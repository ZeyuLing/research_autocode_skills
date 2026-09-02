from __future__ import annotations

import contextlib, ctypes, hashlib, importlib.util, io, json, os, shutil, subprocess, sys, tempfile, threading, time, types, unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock
from pypdf import PdfWriter

sys.dont_write_bytecode = True
SCRIPT = Path(__file__).parents[1] / "scripts" / "manage_review_retry.py"
SPEC = importlib.util.spec_from_file_location("manage_review_retry", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)
LAUNCHER_SCRIPT = Path(__file__).parents[1] / "scripts" / "launch_review_actor.py"
LAUNCHER_SPEC = importlib.util.spec_from_file_location("launch_review_actor_for_retry_test", LAUNCHER_SCRIPT)
LAUNCHER = importlib.util.module_from_spec(LAUNCHER_SPEC); LAUNCHER_SPEC.loader.exec_module(LAUNCHER)

def sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest.upper()

def write_pdf(path: Path, pages: int = 2) -> None:
    writer = PdfWriter()
    for _ in range(pages): writer.add_blank_page(width=612, height=792)
    with path.open("wb") as handle: writer.write(handle)

def write_matching_process(run: Path) -> dict:
    meta=json.loads((run/"orchestration"/MODULE.METADATA_FILE).read_text(encoding="utf-8"))
    pdf=meta["pdf_identity"]
    actors=["P","R1","R2","R3","R4","R5","AI","SA-R1","SA-R2","SA-R3","SA-R4","SA-R5","SA-AI","C","S"]
    process={
        "round_id":meta["round_id"],"retry_id":meta["retry_id"],
        "frozen_pdf_file":pdf["neutral_name"],
        "selected_pdf_sha256":pdf["sha256"],
        "physical_page_count":pdf["page_count"],
        "frozen_at":meta["frozen_at_utc"],
        "degree_level":"doctorate","degree_type":"academic",
        "institution":None,"school_or_department":None,"discipline":None,
        "expected_submission_year":None,"artifact_type":"blind-copy",
        "review_mode":"fresh-rereview","output_language":"zh-CN",
        "governing_rule_urls":[],"governing_local_files":[],
        "decision_regime_status":"skill-default",
        "actor_prompt_sha256":{
            actor:hashlib.sha256(actor.encode("utf-8")).hexdigest().upper()
            for actor in actors
        },
    }
    (run/"round"/MODULE.PROCESS_PARAMETER_FILE).write_text(
        json.dumps(process,ensure_ascii=False,indent=2,sort_keys=True)+"\n",
        encoding="utf-8",
    )
    return process

class ManageReviewRetryTests(unittest.TestCase):
    def run_main(self, args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output): code = MODULE.main(args)
        return code, output.getvalue()

    def init_args(self, workspace, source, run):
        return ["initialize", "--workspace", str(workspace.resolve()),
                "--run-root", str(run.resolve()), "--source-pdf", str(source.resolve()),
                "--neutral-pdf-name", "thesis.pdf", "--expected-sha256", sha256(source),
                "--expected-pages", "2", "--new-round-id", "round-new",
                "--new-retry-id", "retry-new", "--replacement-for", "round-old", "retry-old"]

    def test_control_ids_reject_prompt_and_path_injection_characters(self):
        invalid = (
            "round\nforged",
            "round\rforged",
            "round\u2028forged",
            "round/child",
            "round\\child",
            "-leading",
            "x" * 129,
            "round\x00forged",
        )
        for value in invalid:
            with self.subTest(value=repr(value)):
                with self.assertRaises(MODULE.RetryManagementError):
                    MODULE._control_id(value, "test ID")
        for value in ("r", "round-30a76ddf", "retry_01", "A.B-C_9"):
            with self.subTest(valid=value):
                self.assertEqual(value, MODULE._control_id(value, "test ID"))

    def initialized(self, root):
        workspace = root / "workspace"; workspace.mkdir()
        source = root / "source.pdf"; write_pdf(source)
        run = workspace / "run-new"
        code, output = self.run_main(self.init_args(workspace, source, run))
        self.assertEqual(code, 0, output)
        return workspace, source, run

    def seal_args(self, workspace: Path, run: Path):
        return [
            "seal-process","--workspace",str(workspace.resolve()),
            "--run-root",str(run.resolve()),
            "--expected-metadata-sha256",sha256(run/"orchestration"/MODULE.METADATA_FILE),
            "--expected-process-sha256",sha256(run/"round"/MODULE.PROCESS_PARAMETER_FILE),
        ]

    def verify_seal_args(self, workspace: Path, run: Path, process_hash: str, seal_hash: str):
        return [
            "verify-process-seal","--workspace",str(workspace.resolve()),
            "--run-root",str(run.resolve()),
            "--expected-process-sha256",process_hash,
            "--expected-seal-sha256",seal_hash,
        ]

    def sealed(self, root: Path):
        workspace,_,run=self.initialized(root); write_matching_process(run)
        code,out=self.run_main(self.seal_args(workspace,run)); self.assertEqual(code,0,out)
        payload=json.loads(out.splitlines()[-1])
        return workspace,run,payload["process_sha256"],payload["seal_sha256"]

    def crashed(self, root):
        workspace = root / "workspace"; workspace.mkdir()
        source = root / "source.pdf"; write_pdf(source); run = workspace / "run-new"
        with mock.patch.object(MODULE, "_rename_noreplace", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.run_main(self.init_args(workspace, source, run))
        return workspace, run, next(workspace.glob(f"{MODULE.STAGING_PREFIX}*"))

    def test_initialize_publishes_one_closed_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace, source, run = self.initialized(Path(tmp))
            self.assertEqual({p.name for p in run.iterdir()}, {"round", "views", "orchestration"})
            self.assertEqual((run / "round/thesis.pdf").read_bytes(), source.read_bytes())
            self.assertEqual(list((run / "views").iterdir()), [])
            meta_path = run / "orchestration" / MODULE.METADATA_FILE
            self.assertEqual({p.name for p in meta_path.parent.iterdir()}, {MODULE.METADATA_FILE})
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(meta["schema"], MODULE.METADATA_SCHEMA)
            self.assertEqual(meta["transaction"]["state"], "ready-for-publish")
            self.assertEqual(meta["pdf_identity"]["sha256"], sha256(source))
            self.assertFalse(list(workspace.glob(f"{MODULE.STAGING_PREFIX}*")))

    def test_mismatch_and_existing_target_never_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); workspace=root/"workspace"; workspace.mkdir(); source=root/"s.pdf"; write_pdf(source); run=workspace/"run"
            args=self.init_args(workspace,source,run); args[args.index("--expected-sha256")+1]="0"*64
            self.assertNotEqual(self.run_main(args)[0],0); self.assertFalse(run.exists())
            run.mkdir(); (run/"external").write_text("keep")
            self.assertNotEqual(self.run_main(self.init_args(workspace,source,run))[0],0)
            self.assertEqual((run/"external").read_text(),"keep")

    def test_publish_race_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); workspace=root/"workspace"; workspace.mkdir(); source=root/"s.pdf"; write_pdf(source); run=workspace/"run"
            real=MODULE._rename_noreplace
            def race(src,dst): dst.mkdir(); (dst/"external").write_text("keep"); real(src,dst)
            with mock.patch.object(MODULE,"_rename_noreplace",side_effect=race): code,_=self.run_main(self.init_args(workspace,source,run))
            self.assertNotEqual(code,0); self.assertEqual((run/"external").read_text(),"keep")
            self.assertTrue(list(workspace.glob(f"{MODULE.STAGING_PREFIX}*")))

    def test_crash_list_and_cleanup_verified_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace,run,staging=self.crashed(Path(tmp)); self.assertFalse(run.exists())
            code,out=self.run_main(["list-staging","--workspace",str(workspace.resolve())])
            self.assertEqual(code,0,out); self.assertIn("verified",out)
            code,out=self.run_main(["cleanup-staging","--workspace",str(workspace.resolve()),"--staging-root",str(staging.resolve())])
            self.assertEqual(code,0,out); self.assertFalse(staging.exists())
            self.assertEqual(len(list(workspace.glob("QUARANTINED-STAGING-*"))),1)

    def test_cleanup_refuses_identity_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace,_,staging=self.crashed(Path(tmp)); frozen=staging/"round/thesis.pdf"
            data=frozen.read_bytes(); frozen.unlink(); frozen.write_bytes(data)
            code,_=self.run_main(["cleanup-staging","--workspace",str(workspace.resolve()),"--staging-root",str(staging.resolve())])
            self.assertNotEqual(code,0); self.assertTrue(staging.exists())
            self.assertTrue((staging/"orchestration"/MODULE.METADATA_FILE).exists())

    def test_cleanup_refuses_extra_and_unproven_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace,_,staging=self.crashed(Path(tmp)); (staging/"extra").write_text("x")
            args=["cleanup-staging","--workspace",str(workspace.resolve()),"--staging-root",str(staging.resolve())]
            self.assertNotEqual(self.run_main(args)[0],0); self.assertTrue(staging.exists())
            bogus=workspace/f"{MODULE.STAGING_PREFIX}bogus"; bogus.mkdir()
            code,out=self.run_main(["list-staging","--workspace",str(workspace.resolve())])
            self.assertNotEqual(code,0); self.assertIn("invalid",out); self.assertIn("summary",out)
            args[-1]=str(bogus.resolve()); self.assertNotEqual(self.run_main(args)[0],0); self.assertTrue(bogus.exists())

    def test_quarantine_moves_whole_run_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace,_,run=self.initialized(Path(tmp)); (run/"round/review.txt").write_text("current")
            dst=workspace/"QUARANTINED-run-new"
            args=["quarantine","--workspace",str(workspace.resolve()),"--run-root",str(run.resolve()),"--quarantine-run-root",str(dst.resolve())]
            code,out=self.run_main(args); self.assertEqual(code,0,out); self.assertFalse(run.exists())
            self.assertEqual((dst/"round/review.txt").read_text(),"current")
            payload=json.loads(out)
            metadata_path=dst/"orchestration"/MODULE.METADATA_FILE
            self.assertEqual(payload["round_id"],"round-new")
            self.assertEqual(payload["retry_id"],"retry-new")
            self.assertEqual(payload["metadata_sha256"],sha256(metadata_path))
            self.assertEqual(payload["quarantined_run_root"],str(dst.resolve()))

    def test_process_seal_binds_initialized_metadata_to_final_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace,_,run=self.initialized(Path(tmp)); process=write_matching_process(run)
            args=self.seal_args(workspace,run)
            code,out=self.run_main(args); self.assertEqual(code,0,out)
            seal_path=run/"orchestration"/MODULE.PROCESS_SEAL_FILE
            seal=json.loads(seal_path.read_text(encoding="utf-8"))
            self.assertEqual(seal["schema"],MODULE.PROCESS_SEAL_SCHEMA)
            self.assertEqual(seal["process"]["sha256"],sha256(run/"round"/MODULE.PROCESS_PARAMETER_FILE))
            self.assertEqual(seal["projection"]["frozen_at"],process["frozen_at"])
            verify=self.verify_seal_args(workspace,run,seal["process"]["sha256"],sha256(seal_path))
            code,out=self.run_main(verify); self.assertEqual(code,0,out)
            code,out=self.run_main(args); self.assertEqual(code,2,out)
            self.assertIn("already exists",out)

    @unittest.skipUnless(sys.platform in ("win32","linux"),"kernel lock implementation")
    def test_concurrent_launcher_seal_verifiers_wait_then_all_revalidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace,run,process_hash,seal_hash=self.sealed(Path(tmp))
            started=threading.Barrier(7)

            def launcher_verify():
                started.wait(timeout=5)
                return LAUNCHER.verify_process_seal_binding(
                    run,process_hash,seal_hash
                )

            with mock.patch.object(LAUNCHER,"load_module",return_value=MODULE):
                with ThreadPoolExecutor(max_workers=6) as pool:
                    with MODULE._lock(workspace):
                        futures=[pool.submit(launcher_verify) for _ in range(6)]
                        started.wait(timeout=5)
                        time.sleep(0.1)
                        self.assertTrue(all(not future.done() for future in futures))
                    results=[future.result(timeout=10) for future in futures]
            self.assertEqual(6,len(results))
            self.assertTrue(all(result["process_sha256"]==process_hash for result in results))
            self.assertTrue(all(result["seal_sha256"]==seal_hash for result in results))

    @unittest.skipUnless(sys.platform in ("win32","linux"),"kernel lock implementation")
    def test_seal_verifier_lock_wait_times_out_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace,run,process_hash,seal_hash=self.sealed(Path(tmp))
            with MODULE._lock(workspace), mock.patch.object(
                MODULE,"VERIFY_LOCK_TIMEOUT_SECONDS",0.03
            ), mock.patch.object(MODULE,"VERIFY_LOCK_RETRY_SECONDS",0.005):
                code,out=self.run_main(
                    self.verify_seal_args(workspace,run,process_hash,seal_hash)
                )
            self.assertEqual(2,code,out)
            self.assertIn("workspace kernel lock is held",out)
            self.assertIn("timed out",out)

    def test_windows_verifier_does_not_retry_non_contention_open_failure(self):
        class Kernel:
            def __init__(self):
                self.CreateFileW=mock.Mock(return_value=ctypes.c_void_p(-1).value)
                self.CloseHandle=mock.Mock(return_value=1)

        with tempfile.TemporaryDirectory() as tmp:
            workspace=Path(tmp).resolve(); kernel=Kernel()
            with mock.patch.object(MODULE.sys,"platform","win32"), mock.patch.object(
                MODULE,"_windows_kernel32",return_value=kernel
            ), mock.patch.object(
                MODULE.ctypes,"get_last_error",return_value=5,create=True
            ), mock.patch.object(MODULE.time,"sleep") as sleeper:
                with self.assertRaisesRegex(
                    MODULE.RetryManagementError,"acquisition failed \\(5\\)"
                ):
                    with MODULE._lock(
                        workspace,wait_for_verifier=True,timeout_seconds=1.0
                    ):
                        pass
            self.assertEqual(1,kernel.CreateFileW.call_count)
            sleeper.assert_not_called()

    def test_linux_verifier_retries_only_blocking_lock_contention(self):
        calls=[]

        def flock(_fd, _flags):
            calls.append(1)
            if len(calls)<3:
                raise BlockingIOError()

        fake_fcntl=types.SimpleNamespace(LOCK_EX=1,LOCK_NB=2,flock=flock)
        with tempfile.TemporaryDirectory() as tmp:
            workspace=Path(tmp).resolve()
            with mock.patch.object(MODULE.sys,"platform","linux"), mock.patch.dict(
                sys.modules,{"fcntl":fake_fcntl}
            ), mock.patch.object(MODULE.time,"sleep") as sleeper:
                with MODULE._lock(
                    workspace,
                    wait_for_verifier=True,
                    timeout_seconds=1.0,
                    retry_seconds=0.01,
                ):
                    pass
            self.assertEqual(3,len(calls))
            self.assertEqual(2,sleeper.call_count)

    @unittest.skipUnless(sys.platform in ("win32","linux"),"kernel lock implementation")
    def test_initialize_lock_contention_remains_fail_fast(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); workspace=root/"workspace"; workspace.mkdir()
            source=root/"source.pdf"; write_pdf(source); run=workspace/"run"
            with MODULE._lock(workspace), mock.patch.object(MODULE.time,"sleep") as sleeper:
                code,out=self.run_main(self.init_args(workspace,source,run))
            self.assertEqual(2,code,out)
            self.assertIn("workspace kernel lock is held",out)
            sleeper.assert_not_called()
            self.assertFalse(run.exists())

    def test_process_seal_rejects_every_metadata_projection_mismatch(self):
        mutations={
            "round_id":"wrong-round","retry_id":"wrong-retry",
            "frozen_pdf_file":"wrong.pdf","selected_pdf_sha256":"0"*64,
            "physical_page_count":3,"frozen_at":"2026-01-01T00:00:00+00:00",
        }
        for field,value in mutations.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                workspace,_,run=self.initialized(Path(tmp)); process=write_matching_process(run)
                process[field]=value
                (run/"round"/MODULE.PROCESS_PARAMETER_FILE).write_text(
                    json.dumps(process,indent=2),encoding="utf-8"
                )
                args=self.seal_args(workspace,run)
                code,out=self.run_main(args); self.assertEqual(code,2,out)
                self.assertIn('"status": "error"',out)
                self.assertFalse((run/"orchestration"/MODULE.PROCESS_SEAL_FILE).exists())

    def test_process_or_seal_drift_after_seal_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace,_,run=self.initialized(Path(tmp)); process=write_matching_process(run)
            seal=self.seal_args(workspace,run)
            self.assertEqual(self.run_main(seal)[0],0)
            seal_path=run/"orchestration"/MODULE.PROCESS_SEAL_FILE
            original_process_hash=sha256(run/"round"/MODULE.PROCESS_PARAMETER_FILE)
            original_seal_hash=sha256(seal_path)
            process["institution"]="drift outside the metadata projection"
            (run/"round"/MODULE.PROCESS_PARAMETER_FILE).write_text(
                json.dumps(process,indent=2),encoding="utf-8"
            )
            verify=self.verify_seal_args(workspace,run,original_process_hash,original_seal_hash)
            code,out=self.run_main(verify); self.assertEqual(code,2,out)
            self.assertIn("external Stage-O anchor",out)

    def test_process_seal_external_anchors_and_pre_stage_p_topology(self):
        for mutation in ("metadata-hash","process-hash","view-entry","round-entry"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                workspace,_,run=self.initialized(Path(tmp)); write_matching_process(run)
                args=self.seal_args(workspace,run)
                if mutation=="metadata-hash": args[args.index("--expected-metadata-sha256")+1]="0"*64
                elif mutation=="process-hash": args[args.index("--expected-process-sha256")+1]="0"*64
                elif mutation=="view-entry": (run/"views"/"unexpected").write_text("x")
                else: (run/"round"/"unexpected").write_text("x")
                code,out=self.run_main(args)
                self.assertEqual(code,2,out)
                self.assertFalse((run/"orchestration"/MODULE.PROCESS_SEAL_FILE).exists())

    def test_process_seal_supports_precommitted_stage_v_and_rejects_bad_actor_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace,_,run=self.initialized(Path(tmp)); process=write_matching_process(run)
            process["actor_prompt_sha256"]["V"]=hashlib.sha256(b"V").hexdigest().upper()
            (run/"round"/MODULE.PROCESS_PARAMETER_FILE).write_text(json.dumps(process,indent=2),encoding="utf-8")
            code,out=self.run_main(self.seal_args(workspace,run))
            self.assertEqual(code,0,out)

        with tempfile.TemporaryDirectory() as tmp:
            workspace,_,run=self.initialized(Path(tmp)); process=write_matching_process(run)
            del process["actor_prompt_sha256"]["R5"]
            (run/"round"/MODULE.PROCESS_PARAMETER_FILE).write_text(json.dumps(process,indent=2),encoding="utf-8")
            code,out=self.run_main(self.seal_args(workspace,run))
            self.assertEqual(code,2,out)
            self.assertIn("actor set mismatch",out)

    def test_process_seal_verify_allows_stage_p_outputs_but_rejects_wrong_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace,_,run=self.initialized(Path(tmp)); write_matching_process(run)
            code,out=self.run_main(self.seal_args(workspace,run)); self.assertEqual(code,0,out)
            result=json.loads(out.splitlines()[-1]); process_hash=result["process_sha256"]; seal_hash=result["seal_sha256"]
            (run/"round"/"00-manifest.md").write_text("Stage P has now started",encoding="utf-8")
            verify=self.verify_seal_args(workspace,run,process_hash,seal_hash)
            code,out=self.run_main(verify); self.assertEqual(code,0,out)
            verify[-1]="0"*64
            code,out=self.run_main(verify); self.assertEqual(code,2,out)
            self.assertIn("seal hash differs",out)

    def test_seal_commit_after_create_failure_is_exit_three_and_preserves_seal(self):
        for mutation in ("fsync-failure","seal-replacement"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                workspace,_,run=self.initialized(Path(tmp)); write_matching_process(run)
                seal_path=run/"orchestration"/MODULE.PROCESS_SEAL_FILE
                real=MODULE._fsync_directory; intervened=False
                def intervene(path):
                    nonlocal intervened
                    if not intervened and path==run/"orchestration" and seal_path.exists():
                        intervened=True
                        if mutation=="fsync-failure": raise MODULE.RetryManagementError("simulated seal durability failure")
                        value=seal_path.read_bytes(); seal_path.unlink(); seal_path.write_bytes(value)
                    return real(path)
                with mock.patch.object(MODULE,"_fsync_directory",side_effect=intervene):
                    code,out=self.run_main(self.seal_args(workspace,run))
                self.assertTrue(intervened)
                self.assertEqual(code,3,out)
                self.assertTrue(seal_path.exists())
                self.assertTrue(
                    "sealed_but_durability_uncertain" in out
                    or "process_seal_commit_uncertain" in out,
                    out,
                )

        with tempfile.TemporaryDirectory() as tmp:
            workspace,_,run=self.initialized(Path(tmp)); write_matching_process(run)
            seal=self.seal_args(workspace,run)
            self.assertEqual(self.run_main(seal)[0],0)
            seal_path=run/"orchestration"/MODULE.PROCESS_SEAL_FILE
            original_process_hash=sha256(run/"round"/MODULE.PROCESS_PARAMETER_FILE)
            original_seal_hash=sha256(seal_path)
            value=json.loads(seal_path.read_text(encoding="utf-8")); value["process"]["sha256"]="0"*64
            seal_path.write_text(json.dumps(value,indent=2),encoding="utf-8")
            verify=self.verify_seal_args(workspace,run,original_process_hash,original_seal_hash)
            code,out=self.run_main(verify); self.assertEqual(code,2,out)
            self.assertIn("external Stage-O anchor",out)

    def test_quarantine_race_preserves_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace,_,run=self.initialized(Path(tmp)); dst=workspace/"QUARANTINED-run-new"; real=MODULE._rename_noreplace
            def race(src,target): target.mkdir(); (target/"external").write_text("keep"); real(src,target)
            args=["quarantine","--workspace",str(workspace.resolve()),"--run-root",str(run.resolve()),"--quarantine-run-root",str(dst.resolve())]
            with mock.patch.object(MODULE,"_rename_noreplace",side_effect=race): code,_=self.run_main(args)
            self.assertNotEqual(code,0); self.assertTrue(run.exists()); self.assertEqual((dst/"external").read_text(),"keep")

    def test_quarantine_source_swap_is_commit_identity_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace,_,run=self.initialized(Path(tmp)); dst=workspace/"QUARANTINED-run"; real=MODULE._rename_noreplace
            def swap(source,target):
                aside=workspace/"attacker-aside"; real(source,aside); shutil.copytree(aside,source); real(source,target)
            args=["quarantine","--workspace",str(workspace.resolve()),"--run-root",str(run.resolve()),"--quarantine-run-root",str(dst.resolve())]
            with mock.patch.object(MODULE,"_rename_noreplace",side_effect=swap): code,out=self.run_main(args)
            self.assertEqual(code,3); self.assertIn("commit_identity_failure",out); self.assertTrue(dst.exists())

    def test_old_artifacts_are_never_copied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); workspace=root/"workspace"; workspace.mkdir(); old=workspace/"QUARANTINED-old"; old.mkdir(); (old/"old-report").write_text("x")
            source=root/"s.pdf"; write_pdf(source); run=workspace/"run"
            self.assertEqual(self.run_main(self.init_args(workspace,source,run))[0],0)
            self.assertFalse(any(p.name=="old-report" for p in run.rglob("*")))

    def test_initial_run_needs_no_fictitious_old_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); workspace=root/"workspace"; workspace.mkdir(); source=root/"s.pdf"; write_pdf(source); run=workspace/"run"
            args=self.init_args(workspace,source,run); index=args.index("--replacement-for"); args[index:index+3]=["--initial-run"]
            code,out=self.run_main(args); self.assertEqual(code,0,out)
            meta=json.loads((run/"orchestration"/MODULE.METADATA_FILE).read_text())
            self.assertEqual(meta["replacement_for"],{"round_id":None,"retry_id":None})

    def test_source_swap_at_publish_is_commit_identity_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); workspace=root/"workspace"; workspace.mkdir(); source=root/"s.pdf"; write_pdf(source); run=workspace/"run"; real=MODULE._rename_noreplace
            def swap(staging,destination):
                aside=workspace/"attacker-aside"; real(staging,aside); shutil.copytree(aside,staging); real(staging,destination)
            with mock.patch.object(MODULE,"_rename_noreplace",side_effect=swap): code,out=self.run_main(self.init_args(workspace,source,run))
            self.assertEqual(code,3); self.assertIn("commit_identity_failure",out); self.assertTrue(run.exists())

    def test_same_root_mutation_at_publish_is_commit_identity_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); workspace=root/"workspace"; workspace.mkdir(); source=root/"s.pdf"; write_pdf(source); run=workspace/"run"; real=MODULE._rename_noreplace
            def mutate(staging,destination):
                (staging/"unregistered-old-review.txt").write_text("must not enter a fresh run")
                real(staging,destination)
            with mock.patch.object(MODULE,"_rename_noreplace",side_effect=mutate): code,out=self.run_main(self.init_args(workspace,source,run))
            self.assertEqual(code,3); self.assertIn("commit_identity_failure",out); self.assertTrue(run.exists())

    def test_owned_directory_replacement_at_publish_is_commit_identity_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); workspace=root/"workspace"; workspace.mkdir(); source=root/"s.pdf"; write_pdf(source); run=workspace/"run"; real=MODULE._rename_noreplace
            def replace_owned(staging,destination):
                (staging/"views").rmdir(); (staging/"views").mkdir()
                real(staging,destination)
            with mock.patch.object(MODULE,"_rename_noreplace",side_effect=replace_owned): code,out=self.run_main(self.init_args(workspace,source,run))
            self.assertEqual(code,3); self.assertIn("commit_identity_failure",out); self.assertTrue(run.exists())

    def test_reserved_run_root_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); workspace=root/"workspace"; workspace.mkdir(); source=root/"s.pdf"; write_pdf(source)
            run=workspace/(MODULE.STAGING_PREFIX+"published")
            code,out=self.run_main(self.init_args(workspace,source,run))
            self.assertEqual(code,2); self.assertIn("reserved",out); self.assertFalse(run.exists())

    def test_lexical_symlink_alias_is_rejected_before_canonicalization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); workspace=root/"workspace"; workspace.mkdir(); source=root/"s.pdf"; write_pdf(source)
            alias=root/"workspace-alias"
            try: alias.symlink_to(workspace,target_is_directory=True)
            except OSError: self.skipTest("directory symlink creation unavailable")
            run=workspace/"run"
            args=self.init_args(workspace,source,run)
            args[args.index("--workspace")+1]=str(alias)
            args[args.index("--run-root")+1]=str(alias/"run")
            code,out=self.run_main(args)
            self.assertEqual(code,2,out)
            self.assertIn("reparse/symlink component",out)
            self.assertFalse(run.exists())

    def test_post_commit_fsync_failure_reports_uncertain_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); workspace=root/"workspace"; workspace.mkdir(); source=root/"s.pdf"; write_pdf(source); run=workspace/"run"; real=MODULE._fsync_directory
            def fail_after_commit(path):
                if run.exists() and path==workspace: raise MODULE.RetryManagementError("simulated flush failure")
                return real(path)
            with mock.patch.object(MODULE,"_fsync_directory",side_effect=fail_after_commit): code,out=self.run_main(self.init_args(workspace,source,run))
            self.assertEqual(code,3); self.assertIn("committed_but_durability_uncertain",out); self.assertTrue(run.exists())

    def test_malformed_metadata_is_structured_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace,_,run=self.initialized(Path(tmp)); path=run/"orchestration"/MODULE.METADATA_FILE
            meta=json.loads(path.read_text()); meta["unexpected"]="x"; path.write_text(json.dumps(meta))
            dst=workspace/"QUARANTINED-run"
            code,out=self.run_main(["quarantine","--workspace",str(workspace.resolve()),"--run-root",str(run.resolve()),"--quarantine-run-root",str(dst.resolve())])
            self.assertEqual(code,2); self.assertIn('"status": "error"',out); self.assertTrue(run.exists())

    def test_metadata_is_never_reopened_through_a_replaced_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); workspace=root/"workspace"; workspace.mkdir(); source=root/"s.pdf"; write_pdf(source); run=workspace/"run"; victim=root/"victim.txt"; victim.write_text("DO-NOT-TOUCH",encoding="utf-8")
            real=MODULE._write_meta_handle; calls=0; swapped=False
            def intervene(handle,path,expected,data):
                nonlocal calls,swapped
                calls+=1
                if calls==2:
                    try:
                        path.unlink(); os.link(victim,path); swapped=True
                    except PermissionError:
                        # Windows normally prevents replacement while the metadata
                        # handle is held; that is already the desired safety result.
                        pass
                return real(handle,path,expected,data)
            with mock.patch.object(MODULE,"_write_meta_handle",side_effect=intervene): code,out=self.run_main(self.init_args(workspace,source,run))
            self.assertEqual("DO-NOT-TOUCH",victim.read_text(encoding="utf-8"))
            if swapped:
                self.assertNotEqual(code,0,out)
            else:
                self.assertEqual(code,0,out)

    def test_initialize_rejects_post_handle_metadata_hardlink_or_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); workspace=root/"workspace"; workspace.mkdir(); source=root/"s.pdf"; write_pdf(source); run=workspace/"run"
            external_link=root/"metadata-hardlink.json"; real=MODULE._fsync_directory; intervened=False
            def hardlink_after_handle(path):
                nonlocal intervened
                if not intervened and path.name=="round" and path.parent.name.startswith(MODULE.STAGING_PREFIX):
                    os.link(path.parent/"orchestration"/MODULE.METADATA_FILE,external_link)
                    intervened=True
                return real(path)
            with mock.patch.object(MODULE,"_fsync_directory",side_effect=hardlink_after_handle):
                code,out=self.run_main(self.init_args(workspace,source,run))
            self.assertTrue(intervened)
            self.assertEqual(code,2,out)
            self.assertFalse(run.exists())

        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); workspace=root/"workspace"; workspace.mkdir(); source=root/"s.pdf"; write_pdf(source); run=workspace/"run"
            real=MODULE._fsync_directory; mutated=False
            def mutate_before_success(path):
                nonlocal mutated
                result=real(path)
                if path==workspace and run.exists() and not mutated:
                    (run/"orchestration"/MODULE.METADATA_FILE).write_text("{}",encoding="utf-8")
                    mutated=True
                return result
            with mock.patch.object(MODULE,"_fsync_directory",side_effect=mutate_before_success):
                code,out=self.run_main(self.init_args(workspace,source,run))
            self.assertTrue(mutated)
            self.assertEqual(code,3,out)
            self.assertIn("committed_but_durability_uncertain",out)
            self.assertTrue(run.exists())

    def test_initialize_rejects_process_placeholders_and_nonportable_pdf_names(self):
        for mutation in ("round-id", "pdf-name"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); workspace=root/"workspace"; workspace.mkdir(); source=root/"s.pdf"; write_pdf(source); run=workspace/"run"
                args=self.init_args(workspace,source,run)
                if mutation=="round-id": args[args.index("--new-round-id")+1]="pending"
                else: args[args.index("--neutral-pdf-name")+1]="CON.pdf"
                code,out=self.run_main(args)
                self.assertEqual(code,2,out)
                self.assertFalse(run.exists())

    @unittest.skipUnless(sys.platform in ("win32","linux"),"kernel lock implementation")
    def test_kernel_lock_releases_after_hard_process_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace=Path(tmp).resolve(); code=("import importlib.util,os,pathlib; p=pathlib.Path(r'"+str(SCRIPT)+"'); s=importlib.util.spec_from_file_location('m',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); c=m._lock(pathlib.Path(r'"+str(workspace)+"')); c.__enter__(); os._exit(17)")
            result=subprocess.run([sys.executable,"-B","-c",code],env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"})
            self.assertEqual(result.returncode,17)
            with MODULE._lock(workspace): pass

    def test_kernel_lock_refuses_hardlink_without_touching_victim(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace=Path(tmp).resolve(); victim=workspace/"victim.txt"; victim.write_text("DO-NOT-TOUCH",encoding="utf-8")
            os.link(victim,workspace/MODULE.LOCK_FILE)
            with self.assertRaises(MODULE.RetryManagementError):
                with MODULE._lock(workspace): pass
            self.assertEqual("DO-NOT-TOUCH",victim.read_text(encoding="utf-8"))

    def test_kernel_lock_refuses_symlink_without_touching_victim(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace=Path(tmp).resolve(); victim=workspace/"victim.txt"; victim.write_text("DO-NOT-TOUCH",encoding="utf-8")
            try: (workspace/MODULE.LOCK_FILE).symlink_to(victim)
            except OSError: self.skipTest("symlink creation unavailable")
            with self.assertRaises((MODULE.RetryManagementError,OSError)):
                with MODULE._lock(workspace): pass
            self.assertEqual("DO-NOT-TOUCH",victim.read_text(encoding="utf-8"))

    def test_windows_ctypes_prototypes_are_declared(self):
        class Fn:
            def __call__(self,*args): return 1
        class Kernel:
            def __init__(self):
                self.CreateFileW=Fn(); self.FlushFileBuffers=Fn(); self.CloseHandle=Fn(); self.MoveFileExW=Fn()
        kernel=Kernel()
        with mock.patch.object(MODULE.ctypes,"WinDLL",return_value=kernel,create=True): result=MODULE._windows_kernel32()
        self.assertIs(result,kernel)
        self.assertEqual(len(kernel.CreateFileW.argtypes),7); self.assertIsNotNone(kernel.CreateFileW.restype)
        self.assertEqual(len(kernel.MoveFileExW.argtypes),3); self.assertIsNotNone(kernel.CloseHandle.restype)

    @unittest.skipUnless(sys.platform=="win32","Windows-only")
    def test_windows_no_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); src=root/"src"; dst=root/"dst"; src.mkdir(); dst.mkdir()
            with self.assertRaises(MODULE.RetryManagementError): MODULE._rename_noreplace(src,dst)
            self.assertTrue(src.exists()); self.assertTrue(dst.exists())

    def test_linux_without_renameat2_fails_closed(self):
        class NoRename: pass
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); src=root/"src"; dst=root/"dst"; src.mkdir()
            with mock.patch.object(MODULE.sys,"platform","linux"), mock.patch.object(MODULE.ctypes,"CDLL",return_value=NoRename()):
                with self.assertRaises(MODULE.RetryManagementError): MODULE._rename_noreplace(src,dst)
            self.assertTrue(src.exists()); self.assertFalse(dst.exists())

    def test_unsupported_platform_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); src=root/"src"; dst=root/"dst"; src.mkdir()
            with mock.patch.object(MODULE.sys,"platform","darwin"):
                with self.assertRaises(MODULE.RetryManagementError): MODULE._rename_noreplace(src,dst)
            self.assertTrue(src.exists()); self.assertFalse(dst.exists())

if __name__ == "__main__": unittest.main()
