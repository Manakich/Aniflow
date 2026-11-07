# AniFlow Recap Studio — Full Recap mode

This branch adds a separate **Full Recap Studio** workflow to the AniFlow fork. Existing Dialogue Recap, Narrated Recap and Scene Flow modes remain available.

## Product workflow

1. Load an episode from an existing chapter folder, a supported AniFlow website URL, a single image, a ZIP/CBZ archive, or a PDF.
2. Detect and review art panels in reading order. Full Recap filters exact duplicates, truly blank pages, and likely promotional/decorative panels. Meaningful backgrounds and uncertain panels are retained.
3. Analyse the kept panels, then generate one coherent Russian recap script for the complete episode. The script has semantic visual cues which refer to the original panel IDs.
4. Review and edit the complete script.
5. Select a TTS engine and voice. The complete approved script is sent as **one request** to the selected provider, producing **one continuous audio file**.
6. Align the text to the audio only to place images. The audio is the master clock; it is never cut, split, stretched or shortened to fit the images.
7. Review the visual timeline. You can replace a selected panel in a cue without changing the audio or its timing. Short narration fragments avoid rapid-fire cuts; the current default targets at least about two seconds per visual shot when multiple panels are available.
8. Render one MP4 with subtle Ken Burns motion and optional background music.
9. Upload episode-specific thumbnail and title references. Generate three title options and three different thumbnail concepts at 1280×720.

## Main modules

- `pipeline/full_recap.py`: panel context, filtering, multi-chapter panel IDs, one full-script LLM request and semantic visual cues.
- `pipeline/full_recap_audio.py`: one full-script TTS request; no automatic text chunking.
- `pipeline/elevenlabs_tts.py`: ElevenLabs long-form single-request synthesis with native word alignment.
- `pipeline/audio_alignment.py`: SRT / native TTS / faster-whisper word timings and visual cue-to-panel timeline.
- `pipeline/full_recap_renderer.py`: continuous visual edit under one unmodified narration file.
- `pipeline/full_recap_media.py`: per-video reference storage, title-style analysis, title generation and thumbnail generation.
- `pipeline/downloader.py`: secure ZIP/CBZ import, single-image import and optional PDF rasterization.
- `RECAP_STUDIO.md`: this setup and behaviour reference.

## Local setup (Windows)

Use the existing AniFlow setup first:

```powershell
git clone https://github.com/Manakich/Aniflow.git
cd Aniflow
setup.bat
```

Or, if the repository is already cloned and the base app is installed:

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-optional.txt
copy .env.example .env
python app.py
```

Open the local web UI at `http://localhost:8080`.

## API keys and providers

- **Script model:** uses AniFlow's configured narration backend (for example, Ollama, Gemini, Claude or the configured OpenAI-compatible/9router transport).
- **Russian voice:** Edge TTS can list Russian voices. ElevenLabs requires its API key to be set in the existing voice settings UI.
- **ElevenLabs Full Recap:** defaults to Flash v2.5 and requests the complete script once via the with-timestamps endpoint. The implementation enforces a 40,000-character maximum for Flash v2.5 and a 10,000-character maximum for Multilingual v2. It does not split a longer script. Shorten the story or select a provider/model whose single-request limit can accommodate it.
- **Alignment:** Edge TTS uses its accompanying subtitle stream; ElevenLabs returns timing from the same TTS request. Other providers can use the optional faster-whisper fallback.
- **Thumbnails:** set `OPENAI_API_KEY` in the local `.env` file. Optional model and compatible endpoint settings are `OPENAI_IMAGE_MODEL` and `OPENAI_API_BASE_URL`. The key is read by the local server and must never be committed.
- **PDF:** PyMuPDF is installed from `requirements-optional.txt`.

## Important behaviour and safeguards

- The narration audio is the master clock.
- During a speech pause, the previous image stays on screen.
- The final image remains on screen until the narration file ends.
- Background music is optional and mixed below narration.
- Panel filtering is conservative: if the vision classifier is uncertain, the image is kept.
- Multi-chapter Full Recap assigns chapter-qualified panel IDs to avoid panel ID collisions between chapters.
- References are stored per project. The final YouTube screen has separate upload and clear controls for thumbnail references and title references. A title screenshot or text examples are required for title generation; at least one thumbnail reference is required for cover generation.
- The timeline editor only changes panel selection; saved timestamp boundaries and audio remain unchanged.
- Image generation creates three separate concepts using the episode's selected art panels and uploaded thumbnail references. Russian thumbnail lettering is overlaid after image generation for readable typography.
- Generated titles use episode content and title-style references. They are not copied literally from the reference screenshots.

## Current verification

The GitHub Actions workflow is triggered on each push to the feature branch and checks:
- Python compilation of the application and pipeline modules.
- Full Recap unit tests for full-script generation, single-request TTS, timing alignment, panel filtering, ZIP/CBZ import, multi-chapter IDs, thumbnail/title generation and ElevenLabs alignment.
- JavaScript syntax for the web UI.

Check the pull request's **Checks** tab for the status of the latest branch commit. A green CI run verifies compilation, unit-level behaviour and JS syntax; it does not replace a real local end-to-end episode render.

## Still required before calling it production-ready

- Run the entire pipeline on real user-selected chapters with actual LLM/TTS/image API credentials and inspect the resulting MP4.
- Verify that AniFlow's site scraper can access the specific source site and chapter URLs you plan to use.
- Tune visual cue-to-panel choices against real episodes. The initial multi-panel distribution is intentionally conservative; the review screen lets you replace a wrong visual, but it is not a full professional drag-and-drop NLE.
- Review the generated cover/title style against the supplied channel references and tune prompts based on actual outputs.
- Test the complete install and render on the target Windows machine, GPU, available disk space and chosen TTS provider.

The pull request is intentionally kept as a draft until these real-world checks are completed.