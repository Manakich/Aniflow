# AniFlow Recap Studio — Full Recap mode

This development branch adds a separate chapter-level workflow without removing the existing Dialogue Recap, Narrated Recap, or Scene Flow modes.

## Product contract

1. Detect and review clean art panels in reading order.
2. Build visual notes from the source panels.
3. Generate one continuous Russian recap script with semantic visual cues.
4. Let the user review and edit that complete script.
5. Send the complete approved script to the selected TTS provider once.
6. Use speech timing only to place visuals; never split or re-synthesize narration to fit the pictures.
7. Render one MP4 whose video track covers the entire narration duration.

## New modules

- `pipeline/full_recap.py`: visual context collection and one full-script LLM call.
- `pipeline/full_recap_audio.py`: one TTS invocation for the complete script.
- `pipeline/audio_alignment.py`: SRT/faster-whisper word timing and cue-to-panel timeline.
- `pipeline/full_recap_renderer.py`: continuous visual edit under one narration file.

## Important behavior

- The narration audio is the master clock.
- If a cue is missing or alignment confidence is poor, the renderer uses a chronological fallback rather than inventing a scene.
- During speech pauses, the previous image remains on screen.
- The final visual remains until the narration file ends.
- Background music is optional and mixed below the narration.
- Very large texts must fit the selected TTS provider's single-request limits. This mode deliberately does not auto-chunk the text. When a provider rejects an over-limit script, use a provider/model with a higher single-request limit or edit the script.

## Optional dependency

If a provider does not return word-level boundaries, install:

```bash
pip install -r requirements-optional.txt
```

## Status

The core backend path is under active integration. The next work items are the Flask endpoints, the wizard UI for the full-recap mode, script editing, thumbnail/title generation, and end-to-end testing with real chapter assets and configured API keys.
