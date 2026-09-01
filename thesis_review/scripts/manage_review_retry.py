#!/usr/bin/env python3
"""Fail-closed Stage-O run-container publication and quarantine mechanics."""
from __future__ import annotations

import argparse, contextlib, ctypes, errno, hashlib, json, os, stat, sys, types, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from pypdf import PdfReader

METADATA_SCHEMA="thesis-review-stage-o-run-metadata-v2"
METADATA_FILE="review-retry-metadata.json"
PROCESS_SEAL_SCHEMA="thesis-review-stage-o-process-seal-v1"
PROCESS_SEAL_FILE="process-seal.json"
PROCESS_PARAMETER_FILE="00-process-parameters.json"
LOCK_FILE=".thesis-review-retry.lock"
STAGING_PREFIX=".thesis-review-staging-"
QUARANTINE_PREFIX="QUARANTINED-"
CHILDREN=("round","views","orchestration")

class RetryManagementError(RuntimeError): pass
class CommitStateError(RetryManagementError):
    def __init__(self, status: str, message: str): super().__init__(message); self.status=status

def _windows_kernel32():
    k=ctypes.WinDLL("kernel32",use_last_error=True)
    k.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
    k.CreateFileW.restype=ctypes.c_void_p
    k.FlushFileBuffers.argtypes=[ctypes.c_void_p]; k.FlushFileBuffers.restype=ctypes.c_int
    k.CloseHandle.argtypes=[ctypes.c_void_p]; k.CloseHandle.restype=ctypes.c_int
    k.MoveFileExW.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint32]; k.MoveFileExW.restype=ctypes.c_int
    return k

def _absolute(value: str, label: str) -> Path:
    path=Path(value)
    if not path.is_absolute(): raise RetryManagementError(f"{label} must be absolute")
    if any(part==".." for part in path.parts):
        raise RetryManagementError(f"{label} must not contain lexical parent traversal")
    # Do not call Path.resolve() here: doing so would erase evidence that an
    # explicitly supplied path traversed a symlink or Windows reparse point.
    path=Path(os.path.abspath(os.fspath(path)))
    current=Path(path.anchor)
    for part in path.parts[1:]:
        current=current/part
        if not os.path.lexists(current):
            break
        info=os.lstat(current)
        if stat.S_ISLNK(info.st_mode) or getattr(info,"st_file_attributes",0)&0x400:
            raise RetryManagementError(
                f"{label} traverses a reparse/symlink component: {current}"
            )
    return path

def _direct_child(path: Path, workspace: Path, label: str) -> None:
    if path.parent != workspace or path == workspace: raise RetryManagementError(f"{label} must be a direct child of workspace")

def _identity(path: Path) -> dict[str,int]:
    info=os.lstat(path)
    return {"st_dev":info.st_dev,"st_ino":info.st_ino,"st_mode":info.st_mode}

def _same_identity(path: Path, expected: dict) -> bool:
    try: return _identity(path)==expected
    except FileNotFoundError: return False

def _reject_reparse(path: Path) -> None:
    info=os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or getattr(info,"st_file_attributes",0)&0x400:
        raise RetryManagementError(f"reparse/symlink refused: {path}")

def _scan_no_reparse(root: Path) -> None:
    _reject_reparse(root)
    for current, dirs, files in os.walk(root, followlinks=False):
        for name in dirs+files: _reject_reparse(Path(current)/name)

def _sha(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""): digest.update(chunk)
    return digest.hexdigest().upper()

def _strict_json_bytes(data: bytes, label: str) -> dict:
    def reject_duplicates(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise RetryManagementError(f"{label} contains duplicate JSON key {key!r}")
            result[key]=value
        return result
    try: value=json.loads(data.decode("utf-8"),object_pairs_hook=reject_duplicates)
    except (UnicodeError,json.JSONDecodeError) as exc: raise RetryManagementError(f"invalid {label}: {exc}") from exc
    if not isinstance(value,dict): raise RetryManagementError(f"{label} must be a JSON object")
    return value

def _read_regular_snapshot(path: Path, label: str) -> tuple[bytes,str,dict]:
    try: lexical_before=os.lstat(path)
    except FileNotFoundError as exc: raise RetryManagementError(f"missing {label}: {path}") from exc
    if (
        not stat.S_ISREG(lexical_before.st_mode)
        or getattr(lexical_before,"st_file_attributes",0)&0x400
        or lexical_before.st_nlink!=1
    ): raise RetryManagementError(f"{label} is unsafe, linked, or non-regular")
    with path.open("rb") as handle:
        opened_before=os.fstat(handle.fileno())
        if (
            opened_before.st_dev!=lexical_before.st_dev
            or opened_before.st_ino!=lexical_before.st_ino
            or opened_before.st_nlink!=1
            or not stat.S_ISREG(opened_before.st_mode)
        ): raise RetryManagementError(f"{label} pathname/open identity mismatch")
        data=handle.read()
        opened_after=os.fstat(handle.fileno())
    try: lexical_after=os.lstat(path)
    except FileNotFoundError as exc: raise RetryManagementError(f"{label} disappeared during read") from exc
    stable_fields=("st_dev","st_ino","st_mode","st_nlink","st_size","st_mtime_ns")
    if any(getattr(opened_before,key)!=getattr(opened_after,key) for key in stable_fields) or any(
        getattr(opened_after,key)!=getattr(lexical_after,key) for key in stable_fields
    ) or getattr(lexical_after,"st_file_attributes",0)&0x400:
        raise RetryManagementError(f"{label} changed during snapshot")
    digest=hashlib.sha256(data).hexdigest().upper()
    identity={key:getattr(opened_after,key) for key in stable_fields}
    return data,digest,identity

def _require_regular_snapshot_identity(path: Path, expected: dict, label: str) -> tuple[bytes,str]:
    data,digest,current=_read_regular_snapshot(path,label)
    expected_identity={key:expected[key] for key in current}
    if current!=expected_identity or digest!=expected.get("sha256"):
        raise RetryManagementError(f"{label} no longer names the exclusively created object")
    return data,digest

def _process_projection(meta: dict, process: dict) -> dict:
    pdf=meta["pdf_identity"]
    expected={
        "round_id":meta["round_id"],
        "retry_id":meta["retry_id"],
        "frozen_pdf_file":pdf["neutral_name"],
        "selected_pdf_sha256":pdf["sha256"],
        "physical_page_count":pdf["page_count"],
        "frozen_at":meta["frozen_at_utc"],
    }
    actual={key:process.get(key) for key in expected}
    if actual!=expected:
        mismatches=[key for key in expected if actual[key]!=expected[key]]
        raise RetryManagementError(
            "process envelope does not project initialized run metadata exactly: "
            + ",".join(mismatches)
        )
    return expected

def _canonical_process_validator():
    path=Path(__file__).resolve().with_name("validate_review_bundle.py")
    source,digest,_=_read_regular_snapshot(path,"canonical process validator")
    module=types.ModuleType(f"_thesis_review_process_validator_{digest}")
    module.__file__=str(path)
    module.__package__=""
    try: exec(compile(source,str(path),"exec"),module.__dict__)
    except Exception as exc: raise RetryManagementError(f"cannot load canonical process validator: {exc}") from exc
    return module

def _validate_final_process(round_root: Path, process: dict) -> None:
    validator=_canonical_process_validator(); errors=[]
    prompt_map=process.get("actor_prompt_sha256")
    validated,*_=validator.validate_process(
        round_root,
        errors,
        stage_v_present_override=(
            isinstance(prompt_map,dict) and "V" in prompt_map
        ),
    )
    if errors:
        raise RetryManagementError(
            "final process envelope fails canonical production validation: "
            + "; ".join(errors)
        )
    if validated!=process:
        raise RetryManagementError("canonical process parse differs from the authenticated process snapshot")

def _validate_pre_stage_p_state(run: Path, process: dict) -> None:
    views=run/"views"
    if any(views.iterdir()): raise RetryManagementError("views must be empty before Stage P")
    round_root=run/"round"
    expected={PROCESS_PARAMETER_FILE,str(process["frozen_pdf_file"])}
    expected.update(
        str(item["neutral_file"])
        for item in process.get("governing_local_files",[])
    )
    observed={entry.name for entry in round_root.iterdir()}
    if observed!=expected:
        raise RetryManagementError(
            "pre-Stage-P round topology is not closed; "
            f"missing={sorted(expected-observed)}, extra={sorted(observed-expected)}"
        )
    for name in expected:
        _read_regular_snapshot(round_root/name,f"pre-Stage-P input {name}")

def _pages(path: Path) -> int:
    try: return len(PdfReader(str(path),strict=False).pages)
    except Exception as exc: raise RetryManagementError(f"cannot parse PDF: {exc}") from exc

def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle: os.fsync(handle.fileno())

def _fsync_directory(path: Path) -> None:
    if sys.platform=="win32":
        k=_windows_kernel32()
        h=k.CreateFileW(str(path),0x40000000,7,None,3,0x02000000,None)
        if h in (0,-1,ctypes.c_void_p(-1).value): raise RetryManagementError(f"cannot open directory for flush: {path}")
        try:
            if not k.FlushFileBuffers(h): raise RetryManagementError(f"cannot flush directory: {path}")
        finally: k.CloseHandle(h)
    elif sys.platform.startswith("linux"):
        fd=os.open(path,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
        try: os.fsync(fd)
        finally: os.close(fd)
    else: raise RetryManagementError("durable directory flush unsupported; failing closed")

def _rename_noreplace(source: Path, destination: Path) -> None:
    if source.parent != destination.parent: raise RetryManagementError("atomic rename requires same parent")
    if sys.platform=="win32":
        k=_windows_kernel32()
        if not k.MoveFileExW(str(source),str(destination),0):
            code=ctypes.get_last_error()
            if code in (80,183): raise RetryManagementError(f"destination already exists: {destination}")
            raise RetryManagementError(f"MoveFileExW failed ({code})")
        return
    if sys.platform.startswith("linux"):
        libc=ctypes.CDLL(None,use_errno=True)
        try: fn=libc.renameat2
        except AttributeError as exc: raise RetryManagementError("renameat2 unavailable; failing closed") from exc
        fn.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
        if fn(-100,os.fsencode(source),-100,os.fsencode(destination),1)!=0:
            code=ctypes.get_errno()
            if code==errno.EEXIST: raise RetryManagementError(f"destination already exists: {destination}")
            if code in (errno.ENOSYS,errno.EINVAL,getattr(errno,"ENOTSUP",95)): raise RetryManagementError("no-replace rename unsupported; failing closed")
            raise RetryManagementError(f"renameat2 failed: {os.strerror(code)}")
        return
    raise RetryManagementError("no-replace atomic rename unsupported; failing closed")

@contextlib.contextmanager
def _lock(workspace: Path) -> Iterator[None]:
    lock=workspace/LOCK_FILE
    try: lexical_before=os.lstat(lock)
    except FileNotFoundError: lexical_before=None
    if lexical_before is not None and (
        not stat.S_ISREG(lexical_before.st_mode)
        or getattr(lexical_before,"st_file_attributes",0)&0x400
        or lexical_before.st_nlink!=1
    ):
        raise RetryManagementError("workspace lock path is unsafe or hard-linked")

    def validate_open_lock(open_stat: os.stat_result) -> None:
        if not stat.S_ISREG(open_stat.st_mode) or open_stat.st_nlink!=1:
            raise RetryManagementError("workspace lock object is unsafe or hard-linked")
        try: lexical_now=os.lstat(lock)
        except FileNotFoundError as exc: raise RetryManagementError("workspace lock path disappeared") from exc
        if (
            getattr(lexical_now,"st_file_attributes",0)&0x400
            or lexical_now.st_dev!=open_stat.st_dev
            or lexical_now.st_ino!=open_stat.st_ino
        ):
            raise RetryManagementError("workspace lock pathname does not name the opened lock object")

    handle=None
    if sys.platform=="win32":
        k=_windows_kernel32(); handle=k.CreateFileW(str(lock),0x80000000,0,None,4,0x00200080,None)
        if handle in (0,-1,ctypes.c_void_p(-1).value): raise RetryManagementError("workspace kernel lock is held")
        try:
            os_handle=__import__("msvcrt").open_osfhandle(handle,os.O_RDONLY); handle=None
            with os.fdopen(os_handle,"rb") as stream:
                validate_open_lock(os.fstat(stream.fileno())); yield
        finally:
            if handle is not None: k.CloseHandle(handle)
    elif sys.platform.startswith("linux"):
        import fcntl
        fd=os.open(lock,os.O_CREAT|os.O_RDWR|getattr(os,"O_NOFOLLOW",0),0o600)
        try:
            try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc: raise RetryManagementError("workspace kernel lock is held") from exc
            validate_open_lock(os.fstat(fd)); yield
        finally: os.close(fd)
    else: raise RetryManagementError("kernel lock unsupported; failing closed")

def _assert_metadata_handle_identity(handle, path: Path, expected: dict) -> None:
    info=os.fstat(handle.fileno())
    current={"st_dev":info.st_dev,"st_ino":info.st_ino,"st_mode":info.st_mode}
    if current!=expected or not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
        raise RetryManagementError("metadata handle identity changed or became hard-linked")
    try: lexical=os.lstat(path)
    except FileNotFoundError as exc: raise RetryManagementError("metadata pathname disappeared") from exc
    if (
        getattr(lexical,"st_file_attributes",0)&0x400
        or lexical.st_dev!=info.st_dev
        or lexical.st_ino!=info.st_ino
    ):
        raise RetryManagementError("metadata pathname no longer names the open transaction file")

def _write_meta_handle(handle, path: Path, expected: dict, data: dict) -> None:
    _assert_metadata_handle_identity(handle,path,expected)
    encoded=(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+"\n").encode()
    handle.seek(0); handle.write(encoded); handle.truncate(); handle.flush(); os.fsync(handle.fileno())
    _assert_metadata_handle_identity(handle,path,expected)

def _write_exclusive_regular(path: Path, data: bytes, label: str) -> dict:
    if os.path.lexists(path): raise RetryManagementError(f"{label} already exists")
    opened_by_us=False
    try:
        with path.open("x+b") as handle:
            opened_by_us=True
            opened=os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink!=1:
                raise RetryManagementError(f"new {label} is unsafe or hard-linked")
            lexical=os.lstat(path)
            if (
                getattr(lexical,"st_file_attributes",0)&0x400
                or lexical.st_dev!=opened.st_dev
                or lexical.st_ino!=opened.st_ino
            ): raise RetryManagementError(f"new {label} path/open identity mismatch")
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
            opened_after=os.fstat(handle.fileno()); lexical_after=os.lstat(path)
            if (
                opened_after.st_dev!=opened.st_dev
                or opened_after.st_ino!=opened.st_ino
                or opened_after.st_nlink!=1
                or lexical_after.st_dev!=opened.st_dev
                or lexical_after.st_ino!=opened.st_ino
                or getattr(lexical_after,"st_file_attributes",0)&0x400
            ): raise RetryManagementError(f"new {label} changed during durable write")
            identity={
                "st_dev":opened_after.st_dev,"st_ino":opened_after.st_ino,
                "st_mode":opened_after.st_mode,"st_nlink":opened_after.st_nlink,
                "st_size":opened_after.st_size,"st_mtime_ns":opened_after.st_mtime_ns,
                "sha256":hashlib.sha256(data).hexdigest().upper(),
            }
            return identity
    except FileExistsError as exc: raise RetryManagementError(f"{label} appeared before exclusive create") from exc
    except CommitStateError: raise
    except Exception as exc:
        if opened_by_us:
            raise CommitStateError(
                "process_seal_commit_uncertain",
                f"{label} was exclusively created but its final state is uncertain: {exc}",
            ) from exc
        raise

def _record(path: Path, root: Path, kind: str) -> dict:
    result={"relative_path":path.relative_to(root).as_posix(),"kind":kind,"identity":_identity(path)}
    if kind=="file": result.update({"sha256":_sha(path),"size":path.stat().st_size})
    return result

def _safe_relative(value) -> str:
    if not isinstance(value,str) or not value or "\\" in value: raise RetryManagementError("unsafe owned relative path")
    path=Path(value)
    if path.is_absolute() or any(part in ("",".","..") for part in path.parts): raise RetryManagementError("unsafe owned relative path")
    return path.as_posix()

def _validate_metadata_shape(meta: object) -> dict:
    if not isinstance(meta,dict): raise RetryManagementError("metadata must be an object")
    top={"schema","operation","status","round_id","retry_id","replacement_for","pdf_identity","quarantine_template","transaction","frozen_at_utc"}
    if set(meta)!=top: raise RetryManagementError("metadata top-level keys are not closed")
    if meta["schema"]!=METADATA_SCHEMA or meta["operation"]!="initialize" or meta["status"]!="initialized": raise RetryManagementError("invalid metadata state")
    for key in ("round_id","retry_id","frozen_at_utc"):
        if not isinstance(meta[key],str) or not meta[key]: raise RetryManagementError(f"invalid {key}")
    if meta["round_id"]==meta["retry_id"]: raise RetryManagementError("round and retry IDs must differ")
    replacement=meta["replacement_for"]
    if not isinstance(replacement,dict) or set(replacement)!={"round_id","retry_id"} or not all(v is None or isinstance(v,str) and v for v in replacement.values()): raise RetryManagementError("invalid replacement_for")
    pdf=meta["pdf_identity"]
    if not isinstance(pdf,dict) or set(pdf)!={"neutral_name","sha256","page_count"} or not isinstance(pdf["neutral_name"],str) or not isinstance(pdf["sha256"],str) or len(pdf["sha256"])!=64 or not isinstance(pdf["page_count"],int) or isinstance(pdf["page_count"],bool) or pdf["page_count"]<1: raise RetryManagementError("invalid pdf_identity")
    if not isinstance(meta["quarantine_template"],dict) or set(meta["quarantine_template"])!={"prefix","semantic_content"} or meta["quarantine_template"]!={"prefix":QUARANTINE_PREFIX,"semantic_content":None}: raise RetryManagementError("invalid quarantine template")
    tx=meta["transaction"]
    keys={"transaction_id","state","workspace","publish_run_root","staging_root_name","root_identity","metadata_identity","owned_objects"}
    if not isinstance(tx,dict) or set(tx)!=keys or tx["state"]!="ready-for-publish": raise RetryManagementError("invalid transaction shape/state")
    for key in ("transaction_id","workspace","publish_run_root","staging_root_name"):
        if not isinstance(tx[key],str) or not tx[key]: raise RetryManagementError(f"invalid transaction {key}")
    for ident in (tx["root_identity"],tx["metadata_identity"]):
        if not isinstance(ident,dict) or set(ident)!={"st_dev","st_ino","st_mode"} or not all(isinstance(v,int) and not isinstance(v,bool) for v in ident.values()): raise RetryManagementError("invalid transaction identity")
    records=tx["owned_objects"]
    if not isinstance(records,list): raise RetryManagementError("owned_objects must be a list")
    paths=[]
    for record in records:
        if not isinstance(record,dict) or set(record)!=( {"relative_path","kind","identity"} if record.get("kind")=="directory" else {"relative_path","kind","identity","sha256","size"}): raise RetryManagementError("invalid owned object shape")
        rel=_safe_relative(record["relative_path"]); paths.append(rel)
        if record["kind"] not in ("directory","file") or not isinstance(record["identity"],dict) or set(record["identity"])!={"st_dev","st_ino","st_mode"} or not all(isinstance(v,int) and not isinstance(v,bool) for v in record["identity"].values()): raise RetryManagementError("invalid owned object type/identity")
        mode=record["identity"]["st_mode"]
        if record["kind"]=="directory" and not stat.S_ISDIR(mode) or record["kind"]=="file" and not stat.S_ISREG(mode): raise RetryManagementError("owned kind/mode mismatch")
        if record["kind"]=="file" and (not isinstance(record["sha256"],str) or len(record["sha256"])!=64 or not isinstance(record["size"],int) or isinstance(record["size"],bool) or record["size"]<0): raise RetryManagementError("invalid owned file hash/size")
    expected=["round","views","orchestration",f"round/{pdf['neutral_name']}"]
    if paths!=expected or len(paths)!=len(set(paths)): raise RetryManagementError("owned_objects topology/order is invalid")
    return meta

def _validate_staging(
    staging: Path,
    *,
    expected_metadata: dict | None=None,
    expected_metadata_hash: str | None=None,
) -> dict:
    _scan_no_reparse(staging); meta_path=staging/"orchestration"/METADATA_FILE
    meta_info=os.lstat(meta_path)
    if not stat.S_ISREG(meta_info.st_mode) or meta_info.st_nlink!=1:
        raise RetryManagementError("staging metadata must be one unlinked regular file")
    if expected_metadata_hash is not None and _sha(meta_path)!=expected_metadata_hash:
        raise RetryManagementError("staging metadata content hash differs from the transaction snapshot")
    try: meta=_strict_json_bytes(meta_path.read_bytes(),"staging metadata")
    except Exception as exc: raise RetryManagementError(f"invalid staging metadata: {exc}") from exc
    _validate_metadata_shape(meta)
    if expected_metadata is not None and meta!=expected_metadata:
        raise RetryManagementError("staging metadata differs from the transaction snapshot")
    tx=meta.get("transaction",{})
    if tx.get("staging_root_name")!=staging.name or not _same_identity(staging,tx.get("root_identity",{})): raise RetryManagementError("staging root identity mismatch")
    if not _same_identity(meta_path,tx.get("metadata_identity",{})): raise RetryManagementError("metadata identity mismatch")
    records=tx.get("owned_objects",[]); expected={"orchestration",f"orchestration/{METADATA_FILE}"}
    for record in records:
        rel=record.get("relative_path",""); path=staging/rel; expected.add(rel)
        if not _same_identity(path,record.get("identity",{})): raise RetryManagementError(f"owned object identity mismatch: {rel}")
        if record.get("kind")=="file":
            info=os.lstat(path)
            if info.st_nlink!=1 or _sha(path)!=record.get("sha256") or path.stat().st_size!=record.get("size"):
                raise RetryManagementError(f"owned file content/link mismatch: {rel}")
    actual={p.relative_to(staging).as_posix() for p in staging.rglob("*")}
    if actual!=expected: raise RetryManagementError(f"staging tree is not closed (unexpected/missing objects)")
    return meta

def initialize(args) -> None:
    workspace=_absolute(args.workspace,"workspace"); run=_absolute(args.run_root,"run-root"); source=_absolute(args.source_pdf,"source-pdf")
    if not workspace.is_dir(): raise RetryManagementError("workspace must exist")
    _reject_reparse(workspace); _direct_child(run,workspace,"run-root")
    if run.name in {*CHILDREN,LOCK_FILE} or run.name.startswith((STAGING_PREFIX,QUARANTINE_PREFIX)):
        raise RetryManagementError("run-root uses a reserved Stage-O name")
    if run.exists(): raise RetryManagementError("run-root already exists")
    if source.name==METADATA_FILE or any(p.name.startswith((STAGING_PREFIX,QUARANTINE_PREFIX)) for p in source.parents): raise RetryManagementError("source PDF may not come from staging/quarantine")
    _reject_reparse(source)
    contract=_canonical_process_validator()
    if (
        Path(args.neutral_pdf_name).name!=args.neutral_pdf_name
        or not args.neutral_pdf_name.lower().endswith(".pdf")
        or not contract.is_neutral_portable_basename(args.neutral_pdf_name)
        or contract.portable_basename_key(args.neutral_pdf_name) in contract.RESERVED_ROUND_BASENAME_KEYS
        or contract.RENDER_ARTIFACT_BASENAME_RE.fullmatch(args.neutral_pdf_name)
    ): raise RetryManagementError("neutral PDF name must satisfy the canonical portable, non-reserved process contract")
    expected=args.expected_sha256.upper()
    if len(expected)!=64 or any(ch not in "0123456789ABCDEF" for ch in expected): raise RetryManagementError("expected SHA-256 must be exactly 64 hexadecimal characters")
    if args.expected_pages<1: raise RetryManagementError("expected pages must be positive")
    for label,value in (("round",args.new_round_id),("retry",args.new_retry_id)):
        if (
            not value or contract.is_placeholder(value) or value in CHILDREN
            or value.startswith((STAGING_PREFIX,QUARANTINE_PREFIX))
        ): raise RetryManagementError(f"invalid/reserved {label} ID")
    if args.new_round_id==args.new_retry_id: raise RetryManagementError("round and retry IDs must differ")
    if _sha(source)!=expected or _pages(source)!=args.expected_pages: raise RetryManagementError("source PDF hash/page count mismatch")
    if args.initial_run:
        old_round=old_retry=None
    else:
        if not args.old_round_id or not args.old_retry_id: raise RetryManagementError("replacement run requires both old IDs")
        old_round,args_old_retry=args.old_round_id,args.old_retry_id; old_retry=args_old_retry
        if args.new_round_id in (old_round,old_retry) or args.new_retry_id in (old_round,old_retry): raise RetryManagementError("new identifiers must not inherit old identifiers")
    source_identity=_identity(source)
    staging=None
    with _lock(workspace):
        try:
            staging=workspace/f"{STAGING_PREFIX}{uuid.uuid4().hex}"; staging.mkdir(); root_id=_identity(staging)
            for name in CHILDREN: (staging/name).mkdir()
            meta_path=staging/"orchestration"/METADATA_FILE
            with meta_path.open("x+b") as meta_handle:
                meta_identity=_identity(meta_path)
                _assert_metadata_handle_identity(meta_handle,meta_path,meta_identity)
                meta={"schema":METADATA_SCHEMA,"operation":"initialize","status":"constructing","round_id":args.new_round_id,"retry_id":args.new_retry_id,
                      "replacement_for":{"round_id":old_round,"retry_id":old_retry},
                      "pdf_identity":{"neutral_name":args.neutral_pdf_name,"sha256":expected,"page_count":args.expected_pages},
                      "quarantine_template":{"prefix":QUARANTINE_PREFIX,"semantic_content":None},
                      "transaction":{"transaction_id":uuid.uuid4().hex,"state":"constructing","workspace":str(workspace),"publish_run_root":str(run),"staging_root_name":staging.name,"root_identity":root_id,"metadata_identity":meta_identity,"owned_objects":[]}}
                _write_meta_handle(meta_handle,meta_path,meta_identity,meta)
                if not _same_identity(source,source_identity): raise RetryManagementError("source PDF identity changed before copy")
                frozen=staging/"round"/args.neutral_pdf_name
                with source.open("rb") as src, frozen.open("xb") as dst:
                    while chunk:=src.read(1024*1024): dst.write(chunk)
                    dst.flush(); os.fsync(dst.fileno())
                if not _same_identity(source,source_identity) or _sha(source)!=expected or _sha(frozen)!=expected or _pages(frozen)!=args.expected_pages: raise RetryManagementError("PDF changed during freeze")
                meta["transaction"]["owned_objects"]=[_record(staging/name,staging,"directory") for name in CHILDREN]+[_record(frozen,staging,"file")]
                meta["transaction"]["state"]="ready-for-publish"; meta["status"]="initialized"; meta["frozen_at_utc"]=datetime.now(timezone.utc).isoformat(); _write_meta_handle(meta_handle,meta_path,meta_identity,meta)
            metadata_bytes,metadata_snapshot_hash,metadata_snapshot_identity=_read_regular_snapshot(meta_path,"staging metadata")
            if (
                metadata_snapshot_identity["st_dev"]!=meta_identity["st_dev"]
                or metadata_snapshot_identity["st_ino"]!=meta_identity["st_ino"]
                or _strict_json_bytes(metadata_bytes,"staging metadata")!=meta
            ): raise RetryManagementError("staging metadata differs from the closed transaction handle")
            for name in CHILDREN: _fsync_directory(staging/name)
            _fsync_directory(staging); _fsync_directory(workspace)
            checked=_validate_staging(
                staging,
                expected_metadata=meta,
                expected_metadata_hash=metadata_snapshot_hash,
            ); commit_identity=checked["transaction"]["root_identity"]
            if not _same_identity(staging,commit_identity) or not _same_identity(source,source_identity): raise RetryManagementError("source/staging identity changed at commit boundary")
            _rename_noreplace(staging,run); staging=None
            try:
                if not _same_identity(run,commit_identity): raise CommitStateError("commit_identity_failure","published destination identity differs from committed source")
                _validate_published_identity(
                    run,
                    commit_identity,
                    expected_metadata=checked,
                    expected_metadata_hash=metadata_snapshot_hash,
                    require_initial_closed_tree=True,
                    require_publish_location=True,
                )
            except CommitStateError: raise
            except Exception as exc: raise CommitStateError("commit_identity_failure",str(exc)) from exc
            try:
                _fsync_directory(workspace)
                _validate_published_identity(
                    run,
                    commit_identity,
                    expected_metadata=checked,
                    expected_metadata_hash=metadata_snapshot_hash,
                    require_initial_closed_tree=True,
                    require_publish_location=True,
                )
            except Exception as exc: raise CommitStateError("committed_but_durability_uncertain",str(exc)) from exc
        except Exception:
            # Never physically delete a failed transaction.  A verified residue
            # remains available to list-staging/cleanup-staging isolation.
            raise
    return {
        "metadata_sha256":metadata_snapshot_hash,
        "pdf_sha256":expected,
        "physical_page_count":args.expected_pages,
        "frozen_at_utc":meta["frozen_at_utc"],
    }

def _isolate_verified(staging: Path, workspace: Path) -> Path:
    meta=_validate_staging(staging); root_id=meta["transaction"]["root_identity"]
    if not _same_identity(staging,root_id): raise RetryManagementError("staging root replaced before isolation")
    destination=workspace/f"{QUARANTINE_PREFIX}STAGING-{uuid.uuid4().hex}"
    _validate_staging(staging)
    _rename_noreplace(staging,destination)
    try:
        _validate_published_identity(
            destination,
            root_id,
            expected_metadata=meta,
            require_initial_closed_tree=True,
        )
    except Exception as exc: raise CommitStateError("commit_identity_failure",f"staging isolation identity failure: {exc}") from exc
    try: _fsync_directory(workspace)
    except Exception as exc: raise CommitStateError("committed_but_durability_uncertain",str(exc)) from exc
    return destination

def cleanup_staging(args) -> None:
    workspace=_absolute(args.workspace,"workspace"); staging=_absolute(args.staging_root,"staging-root"); _direct_child(staging,workspace,"staging-root")
    if not staging.name.startswith(STAGING_PREFIX): raise RetryManagementError("not a tool staging root")
    with _lock(workspace):
        destination=_isolate_verified(staging,workspace)
        print(json.dumps({"isolation":"recoverable","quarantined_staging":str(destination)},sort_keys=True))

def list_staging(args) -> None:
    workspace=_absolute(args.workspace,"workspace")
    if not workspace.is_dir(): raise RetryManagementError("workspace must exist")
    total=invalid=0
    for path in sorted(workspace.glob(f"{STAGING_PREFIX}*")):
        total+=1
        try: meta=_validate_staging(path); print(json.dumps({"path":str(path),"state":meta["transaction"]["state"],"validation":"verified"},sort_keys=True))
        except Exception as exc: invalid+=1; print(json.dumps({"path":str(path),"validation":"invalid","error":str(exc)},sort_keys=True))
    print(json.dumps({"summary":{"total":total,"invalid":invalid}},sort_keys=True))
    if invalid: raise RetryManagementError(f"{invalid} invalid staging entr{'y' if invalid==1 else 'ies'}")

def _validate_published_identity(
    run: Path,
    expected_root: dict | None=None,
    *,
    expected_metadata: dict | None=None,
    expected_metadata_hash: str | None=None,
    require_initial_closed_tree: bool=False,
    require_publish_location: bool=False,
) -> dict:
    _scan_no_reparse(run); meta_path=run/"orchestration"/METADATA_FILE
    meta_info=os.lstat(meta_path)
    if not stat.S_ISREG(meta_info.st_mode) or meta_info.st_nlink!=1:
        raise RetryManagementError("published metadata must be one unlinked regular file")
    if expected_metadata_hash is not None and _sha(meta_path)!=expected_metadata_hash:
        raise RetryManagementError("published metadata content hash differs from the committed snapshot")
    try: meta=_strict_json_bytes(meta_path.read_bytes(),"run metadata")
    except Exception as exc: raise RetryManagementError(f"invalid run metadata: {exc}") from exc
    _validate_metadata_shape(meta)
    if expected_metadata is not None and meta != expected_metadata:
        raise RetryManagementError("destination metadata differs from the pre-commit snapshot")
    if expected_root is not None and not _same_identity(run,expected_root): raise RetryManagementError("destination identity differs from commit identity")
    tx=meta["transaction"]
    if not _same_identity(run,tx.get("root_identity",{})): raise RetryManagementError("published run identity mismatch")
    if not _same_identity(meta_path,tx.get("metadata_identity",{})):
        raise RetryManagementError("published metadata identity mismatch")
    if require_publish_location:
        expected_path=Path(tx["publish_run_root"]).resolve(strict=False)
        expected_workspace=Path(tx["workspace"]).resolve(strict=False)
        if run.resolve(strict=False)!=expected_path or run.parent.resolve(strict=False)!=expected_workspace:
            raise RetryManagementError("published run path/workspace differs from the frozen transaction")
    for record in tx["owned_objects"]:
        owned=run/record["relative_path"]
        if not _same_identity(owned,record["identity"]):
            raise RetryManagementError(f"published owned object identity mismatch: {record['relative_path']}")
        if record["kind"]=="file":
            owned_info=os.lstat(owned)
            if (
                owned_info.st_nlink!=1
                or owned.stat().st_size!=record["size"]
                or _sha(owned)!=record["sha256"]
            ):
                raise RetryManagementError(f"published owned file content/link mismatch: {record['relative_path']}")
    frozen=run/"round"/meta["pdf_identity"]["neutral_name"]
    record=next((r for r in meta["transaction"]["owned_objects"] if r["relative_path"]==f"round/{frozen.name}"),None)
    if (
        record is None
        or record["sha256"]!=meta["pdf_identity"]["sha256"]
        or not _same_identity(frozen,record["identity"])
        or frozen.stat().st_size!=record["size"]
        or _sha(frozen)!=record["sha256"]
        or _pages(frozen)!=meta["pdf_identity"]["page_count"]
    ): raise RetryManagementError("frozen PDF identity mismatch")
    if require_initial_closed_tree:
        expected={"round","views","orchestration",f"orchestration/{METADATA_FILE}",f"round/{frozen.name}"}
        actual={path.relative_to(run).as_posix() for path in run.rglob("*")}
        if actual!=expected:
            raise RetryManagementError("published initial run tree is not closed")
    return meta

def _validate_run(run: Path) -> dict:
    return _validate_published_identity(run,require_publish_location=True)

def _seal_file_record(relative_path: str, digest: str, identity: dict) -> dict:
    return {
        "relative_path":relative_path,
        "sha256":digest,
        "size":identity["st_size"],
        "identity":{
            "st_dev":identity["st_dev"],"st_ino":identity["st_ino"],
            "st_mode":identity["st_mode"],"st_nlink":identity["st_nlink"],
            "st_mtime_ns":identity["st_mtime_ns"],
        },
    }

def _expected_sha256(value: str, label: str) -> str:
    normalized=str(value).upper()
    if len(normalized)!=64 or any(ch not in "0123456789ABCDEF" for ch in normalized):
        raise RetryManagementError(f"{label} must be exactly 64 hexadecimal characters")
    return normalized

def _verify_process_seal_locked(
    workspace: Path,
    run: Path,
    expected_process_hash: str,
    expected_seal_hash: str,
) -> dict:
    expected_process_hash=_expected_sha256(expected_process_hash,"expected process SHA-256")
    expected_seal_hash=_expected_sha256(expected_seal_hash,"expected seal SHA-256")
    checked=_validate_run(run); initial_root=checked["transaction"]["root_identity"]
    metadata_path=run/"orchestration"/METADATA_FILE
    process_path=run/"round"/PROCESS_PARAMETER_FILE
    seal_path=run/"orchestration"/PROCESS_SEAL_FILE
    metadata_bytes,metadata_hash,metadata_identity=_read_regular_snapshot(metadata_path,"run metadata")
    process_bytes,process_hash,process_identity=_read_regular_snapshot(process_path,"process envelope")
    seal_bytes,seal_hash,seal_identity=_read_regular_snapshot(seal_path,"process seal")
    if process_hash!=expected_process_hash: raise RetryManagementError("process hash differs from the external Stage-O anchor")
    if seal_hash!=expected_seal_hash: raise RetryManagementError("seal hash differs from the external Stage-O anchor")
    metadata=_strict_json_bytes(metadata_bytes,"run metadata"); _validate_metadata_shape(metadata)
    if metadata!=checked: raise RetryManagementError("run metadata snapshot differs from validated run metadata")
    process=_strict_json_bytes(process_bytes,"process envelope")
    _validate_final_process(run/"round",process)
    projection=_process_projection(metadata,process)
    seal=_strict_json_bytes(seal_bytes,"process seal")
    expected={
        "schema":PROCESS_SEAL_SCHEMA,
        "transaction":{
            "transaction_id":metadata["transaction"]["transaction_id"],
            "run_root_identity":initial_root,
        },
        "metadata":_seal_file_record(
            f"orchestration/{METADATA_FILE}",metadata_hash,metadata_identity
        ),
        "process":_seal_file_record(
            f"round/{PROCESS_PARAMETER_FILE}",process_hash,process_identity
        ),
        "projection":projection,
    }
    if seal!=expected: raise RetryManagementError("process seal does not match current metadata/process identities, bytes, and projection")
    _validate_published_identity(
        run,
        initial_root,
        expected_metadata=metadata,
        expected_metadata_hash=metadata_hash,
        require_publish_location=True,
    )
    for path,label,digest,identity in (
        (metadata_path,"run metadata",metadata_hash,metadata_identity),
        (process_path,"process envelope",process_hash,process_identity),
        (seal_path,"process seal",seal_hash,seal_identity),
    ):
        _,digest_after,identity_after=_read_regular_snapshot(path,label)
        if digest_after!=digest or identity_after!=identity:
            raise RetryManagementError(f"{label} changed across process-seal verification")
    return {
        "metadata_sha256":metadata_hash,
        "process_sha256":process_hash,
        "seal_sha256":seal_hash,
        "seal_file":f"orchestration/{PROCESS_SEAL_FILE}",
    }

def seal_process(args) -> dict:
    workspace=_absolute(args.workspace,"workspace"); run=_absolute(args.run_root,"run-root")
    if not workspace.is_dir(): raise RetryManagementError("workspace must exist")
    _reject_reparse(workspace); _direct_child(run,workspace,"run-root")
    expected_metadata_hash=_expected_sha256(args.expected_metadata_sha256,"expected metadata SHA-256")
    expected_process_hash=_expected_sha256(args.expected_process_sha256,"expected process SHA-256")
    with _lock(workspace):
        checked=_validate_run(run); initial_root=checked["transaction"]["root_identity"]
        metadata_path=run/"orchestration"/METADATA_FILE
        process_path=run/"round"/PROCESS_PARAMETER_FILE
        seal_path=run/"orchestration"/PROCESS_SEAL_FILE
        metadata_bytes,metadata_hash,metadata_identity=_read_regular_snapshot(metadata_path,"run metadata")
        process_bytes,process_hash,process_identity=_read_regular_snapshot(process_path,"process envelope")
        if metadata_hash!=expected_metadata_hash: raise RetryManagementError("metadata hash differs from the external Stage-O anchor")
        if process_hash!=expected_process_hash: raise RetryManagementError("process hash differs from the external Stage-O anchor")
        metadata=_strict_json_bytes(metadata_bytes,"run metadata"); _validate_metadata_shape(metadata)
        if metadata!=checked: raise RetryManagementError("run metadata snapshot differs from validated run metadata")
        process=_strict_json_bytes(process_bytes,"process envelope")
        _validate_final_process(run/"round",process)
        projection=_process_projection(metadata,process)
        _validate_pre_stage_p_state(run,process)
        directory_identities={name:_identity(run/name) for name in CHILDREN}
        _validate_published_identity(
            run,
            initial_root,
            expected_metadata=metadata,
            expected_metadata_hash=metadata_hash,
            require_publish_location=True,
        )
        if any(not _same_identity(run/name,identity) for name,identity in directory_identities.items()):
            raise RetryManagementError("owned run directory changed before process-seal create")
        seal={
            "schema":PROCESS_SEAL_SCHEMA,
            "transaction":{
                "transaction_id":metadata["transaction"]["transaction_id"],
                "run_root_identity":initial_root,
            },
            "metadata":_seal_file_record(
                f"orchestration/{METADATA_FILE}",metadata_hash,metadata_identity
            ),
            "process":_seal_file_record(
                f"round/{PROCESS_PARAMETER_FILE}",process_hash,process_identity
            ),
            "projection":projection,
        }
        encoded=(json.dumps(seal,ensure_ascii=False,indent=2,sort_keys=True)+"\n").encode("utf-8")
        seal_hash=hashlib.sha256(encoded).hexdigest().upper()
        created_identity=_write_exclusive_regular(seal_path,encoded,"process seal")
        try:
            _fsync_directory(run/"orchestration"); _fsync_directory(run); _fsync_directory(workspace)
        except Exception as exc:
            raise CommitStateError("sealed_but_durability_uncertain",str(exc)) from exc
        try:
            _require_regular_snapshot_identity(seal_path,created_identity,"process seal")
            if any(not _same_identity(run/name,identity) for name,identity in directory_identities.items()):
                raise RetryManagementError("owned run directory changed after process-seal create")
            result=_verify_process_seal_locked(
                workspace,run,expected_process_hash,seal_hash
            )
            _require_regular_snapshot_identity(seal_path,created_identity,"process seal")
            return result
        except CommitStateError: raise
        except Exception as exc:
            raise CommitStateError("process_seal_commit_uncertain",str(exc)) from exc

def verify_process_seal(args) -> dict:
    workspace=_absolute(args.workspace,"workspace"); run=_absolute(args.run_root,"run-root")
    if not workspace.is_dir(): raise RetryManagementError("workspace must exist")
    _reject_reparse(workspace); _direct_child(run,workspace,"run-root")
    with _lock(workspace):
        return _verify_process_seal_locked(
            workspace,run,args.expected_process_sha256,args.expected_seal_sha256
        )

def quarantine(args) -> None:
    workspace=_absolute(args.workspace,"workspace"); run=_absolute(args.run_root,"run-root"); dest=_absolute(args.quarantine_run_root,"quarantine-run-root")
    _direct_child(run,workspace,"run-root"); _direct_child(dest,workspace,"quarantine-run-root")
    if not dest.name.startswith(QUARANTINE_PREFIX): raise RetryManagementError("quarantine destination must start QUARANTINED-")
    if dest.exists(): raise RetryManagementError("quarantine destination exists")
    checked=_validate_run(run); source_identity=checked["transaction"]["root_identity"]
    with _lock(workspace):
        _validate_published_identity(run,source_identity)
        if dest.exists(): raise RetryManagementError("quarantine destination appeared")
        if not _same_identity(run,source_identity): raise RetryManagementError("run identity changed at quarantine boundary")
        _rename_noreplace(run,dest)
        try:
            _validate_published_identity(
                dest,
                source_identity,
                expected_metadata=checked,
            )
        except Exception as exc: raise CommitStateError("commit_identity_failure",str(exc)) from exc
        try: _fsync_directory(workspace)
        except Exception as exc: raise CommitStateError("committed_but_durability_uncertain",str(exc)) from exc

def parser() -> argparse.ArgumentParser:
    p=argparse.ArgumentParser(); subs=p.add_subparsers(dest="command",required=True)
    i=subs.add_parser("initialize",description="Build a fresh run in hidden staging and atomically publish it without inheriting old reports.")
    for flag in ("workspace","run-root","source-pdf","neutral-pdf-name","expected-sha256","new-round-id","new-retry-id"): i.add_argument(f"--{flag}",required=True,dest=flag.replace("-","_"))
    mode=i.add_mutually_exclusive_group(required=True); mode.add_argument("--initial-run",action="store_true")
    mode.add_argument("--replacement-for",nargs=2,metavar=("OLD_ROUND_ID","OLD_RETRY_ID"))
    i.set_defaults(old_round_id=None,old_retry_id=None)
    i.add_argument("--expected-pages",required=True,type=int); i.set_defaults(func=initialize)
    q=subs.add_parser("quarantine")
    for flag in ("workspace","run-root","quarantine-run-root"): q.add_argument(f"--{flag}",required=True,dest=flag.replace("-","_"))
    q.set_defaults(func=quarantine)
    l=subs.add_parser("list-staging",description="Audit hidden staging residues; returns nonzero when any entry is invalid."); l.add_argument("--workspace",required=True); l.set_defaults(func=list_staging)
    c=subs.add_parser("cleanup-staging",description="Compatibility name: atomically isolate verified staging as recoverable QUARANTINED-STAGING; never deletes it."); c.add_argument("--workspace",required=True); c.add_argument("--staging-root",required=True); c.set_defaults(func=cleanup_staging)
    for name,func,description in (
        ("seal-process",seal_process,"Exclusively bind the initialized run metadata to the final process envelope before Stage P."),
        ("verify-process-seal",verify_process_seal,"Reverify the immutable metadata/process binding before Stage P dispatch."),
    ):
        command=subs.add_parser(name,description=description)
        command.add_argument("--workspace",required=True)
        command.add_argument("--run-root",required=True,dest="run_root")
        if name=="seal-process":
            command.add_argument("--expected-metadata-sha256",required=True,dest="expected_metadata_sha256")
        command.add_argument("--expected-process-sha256",required=True,dest="expected_process_sha256")
        if name=="verify-process-seal":
            command.add_argument("--expected-seal-sha256",required=True,dest="expected_seal_sha256")
        command.set_defaults(func=func)
    return p

def main(argv=None) -> int:
    try:
        args=parser().parse_args(argv)
        if getattr(args,"replacement_for",None): args.old_round_id,args.old_retry_id=args.replacement_for
        result=args.func(args)
        payload={"command":args.command,"status":"ok"}
        if isinstance(result,dict): payload.update(result)
        print(json.dumps(payload,sort_keys=True)); return 0
    except CommitStateError as exc: print(json.dumps({"status":exc.status,"error":str(exc)},sort_keys=True)); return 3
    except (RetryManagementError,KeyError,TypeError,ValueError,json.JSONDecodeError) as exc: print(json.dumps({"status":"error","error":str(exc)},sort_keys=True)); return 2
    except Exception as exc:
        # A kernel-lock release or other post-body failure must not erase the
        # observable fact that the atomic destination may already exist.
        committed=None
        if getattr(args,"command",None)=="initialize": committed=Path(args.run_root)
        elif getattr(args,"command",None)=="quarantine": committed=Path(args.quarantine_run_root)
        if committed is not None and committed.exists():
            print(json.dumps({"status":"committed_but_durability_uncertain","error":str(exc)},sort_keys=True)); return 3
        print(json.dumps({"status":"error","error":str(exc)},sort_keys=True)); return 2

if __name__=="__main__": raise SystemExit(main())
