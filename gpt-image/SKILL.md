---
name: gpt-image
description: "Use this skill as a prompt/reference layer for GPT Image-style generation or editing requests. Search the bundled Reference Gallery/craft files, shape a strong prompt, then delegate execution directly to the installed `.system/imagegen` skill and its built-in `image_gen` tool. Do not call OpenAI clients, the packaged `gpt-image` CLI, `uvx`, or `scripts/generate.py` for normal image requests."
compatibility: "Codex-local wrapper over `/root/.codex/skills/.system/imagegen`; no `OPENAI_API_KEY`, `gpt-image` CLI, `uv`, or `uvx` is required unless the system `imagegen` skill's explicit fallback flow is separately requested by the user."
metadata: {"delegates_to":"imagegen","delegate_skill":"/root/.codex/skills/.system/imagegen/SKILL.md","homepage":"https://github.com/wuyoscar/gpt_image_2_skill"}
---

# gpt-image

Codex-local prompt/reference layer for image generation and editing.

This skill does not execute image model calls itself. It enriches the user's image request with the bundled gallery and craft references, then hands execution to the system `imagegen` skill at `/root/.codex/skills/.system/imagegen/SKILL.md`. The system `imagegen` skill owns model/tool selection, built-in `image_gen` calls, transparent-background handling, local image loading, save-path policy, and any explicit CLI fallback.

## Core Rule

For normal image generation or editing:

1. Use this skill to classify the request, inspect the gallery/craft references, and prepare the final prompt.
2. Then use the `imagegen` skill directly.
3. In `imagegen`, follow the default built-in path and call the built-in `image_gen` tool.

Do not import or instantiate an OpenAI client. Do not run `gpt-image`, `uvx`, `uv tool run`, or `scripts/generate.py`. Do not create ad-hoc SDK wrappers.

## Operating Loop

1. **Classify the request**: `generate`, `edit`, `transparent/cutout`, `multi-reference`, or `batch/variants`. Identify asset type, exact text, intended use, input image roles, constraints, and whether the asset is preview-only or project-bound.
2. **Search references first**: open `references/gallery.md`; load the closest `references/gallery-<category>.md` file. Use 1 category for normal requests and 2-3 for hybrids. Read actual `**Prompt**` text before adapting a pattern.
3. **Refine with craft**: load `references/craft.md` for dense text, diagrams, UI, data visualization, prompt repair, edit invariants, or multi-panel consistency.
4. **Prepare the imagegen handoff**: write a concise production prompt using the schema below. Include exact text verbatim, input-image roles, invariants for edits, and avoid constraints.
5. **Delegate to `imagegen`**: follow `/root/.codex/skills/.system/imagegen/SKILL.md`.
   - Use built-in `image_gen` by default.
   - For local edit targets, load the file with `view_image` first so it is visible in conversation context.
   - For transparent outputs, use `imagegen`'s built-in-first chroma-key workflow and helper script.
   - Only use `imagegen`'s CLI fallback when the user explicitly asks for it or explicitly confirms a true-transparent fallback described by `imagegen`.
6. **Report through imagegen rules**: final saved path(s), final prompt or prompt set, and whether the built-in tool or an explicitly confirmed fallback was used.

Fast path: for a precise "generate now" request, do a quick reference/craft check, shape the prompt, and immediately delegate to `imagegen` built-in mode.

## Execution Boundaries

- This skill has no direct API/client execution path.
- `scripts/generate.py` is disabled in this local Codex install and exists only to prevent accidental legacy CLI use.
- `references/openai-cookbook.md` may be used for prompt/model-behavior context only; do not treat its client snippets as execution instructions.
- Do not ask for, print, write, or modify `OPENAI_API_KEY` for normal image requests.
- Do not switch to any CLI/model fallback just because the user asks for quality, size, variants, batching, file-path control, or ordinary edits. Let `imagegen` decide the built-in path and save handling.
- If the user explicitly asks for a CLI/API/client implementation task, treat that as code work on this repo, not as the normal image-generation path.

## Reference Loading

- `references/gallery.md`: routing index for the Reference Gallery Atlas. Load first.
- `references/gallery-*.md`: concrete prompt examples, previews, metadata, and attribution. Load the smallest useful slice.
- `references/craft.md`: prompt-craft checklist for exact text, UI/data/diagram grammar, edit invariants, and multi-panel consistency.
- `references/openai-cookbook.md`: optional background reference for model behavior; not an execution guide in Codex.

Reference loading policy: load the smallest useful slice; never load all category files by default.

## Prompt Handoff Schema

Use only the lines that help:

```text
Use case: <generate/edit taxonomy or plain category>
Asset type: <where the asset will be used>
Primary request: <user's main prompt>
Input images: <Image 1: role; Image 2: role> (optional)
Scene/backdrop: <environment>
Subject: <main subject>
Style/medium: <photo/illustration/3D/etc>
Composition/framing: <wide/close/top-down; placement>
Lighting/mood: <lighting + mood>
Color palette: <palette notes>
Materials/textures: <surface details>
Text (verbatim): "<exact text>"
Constraints: <must keep/must avoid>
Avoid: <negative constraints>
```

For edits, repeat invariants clearly: change only the requested element; preserve identity, pose, layout, lighting, text, and other untouched areas as applicable.

For transparent/cutout requests, do not invent a transparent API call. Hand the request to `imagegen`, which uses built-in `image_gen` with a removable chroma-key background first and asks before any true-transparent CLI fallback.

## Verification

Before delegating, confirm internally:

- intent: generate vs edit
- input image roles and local-file visibility needs
- reference category used
- exact text and constraints
- preview-only vs project-bound output

After `imagegen` completes, follow its save-path policy. Project-bound assets must be copied or moved into the workspace; preview-only assets may remain under `$CODEX_HOME/generated_images/...` and be rendered inline.

Preserve `Curated` vs `Author + Source` metadata when adapting gallery examples.
