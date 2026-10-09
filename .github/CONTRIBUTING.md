# Contributing

Small, focused improvements are welcome. For a new feature, open an issue first
to explain the problem and proposed behavior. Audio Forge aims to remain a
simple local converter with a complete, usable interface.

1. Fork the repository and create a branch.
2. Follow [the development setup](../docs/BUILDING.md).
3. Make the change and run the relevant tests. Conversion changes should be
   checked with real FFmpeg processes, including metadata and artwork.
4. For UI changes, check the native macOS window, keyboard navigation, and all
   three interface languages. Include a screenshot when the layout changes.
5. Open a pull request explaining the user-visible change and how you tested it.

Use English for issues, pull requests, code comments, and documentation. Keep
the English, Simplified Chinese, and Japanese dictionaries in `src/audio_forge/web/locales.json`
complete, with matching keys and formatting placeholders. Do not commit music,
credentials, application bundles, generated installers, or downloaded sources.
Do not add a dependency when the standard library or system frameworks can do
the job well. Contributions are licensed under the project's MIT License.
