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
- The final YouTube package can use uploaded thumbnail-style references and title screenshots for each episode.
- Three thumbnail concepts are generated from separate prompts with the selected art panels and reference images. Russian thumbnail lettering is overlaid using Pillow after image generation.
- Three title options are generated using the actual episode script and the uploaded title-style references.
- Thumbnail generation requires `OPENAI_API_KEY` in the local `.env` file. The default image model is `gpt-image-2.5-sunburst`; `gpt-image-2.5-flare` is also available.
- Do not commit the local `.env` file. The API key is read only by the local server.
- Very large texts must fit the selected TTS provider's single-request limits. This mode deliberately does not auto-chunk the text. When a provider rejects an over-limit script, use a provider/model with a higher single-request limit or edit the script.

## Thumbnail and title setup

1. Copy `.env.example` to `.env` if you have not already done so.
2. Set `OPENAI_API_KEY` in `.env` for reference-guided thumbnail generation.
3. Restart AniFlow after changing the environment.
4. In the final Full Recap step, upload thumbnail style references and title screenshots for that video, then generate the three options.

The Images API accepts reference images on its edit endpoint. AniFlow supplies the uploaded references together with selected episode panels, requests 1280×720 artwork, and adds the Russian hook text after generation.

## Optional dependency

If a provider does not return word-level boundaries, install:

```bash
pip install -r requirements-optional.txt
```

## Status

The core backend path is under active integration. The next work items are the Flask endpoints, the wizard UI for the full-recap mode, script editing, thumbnail/title generation, and end-to-end testing with real chapter assets and configured API keys.
