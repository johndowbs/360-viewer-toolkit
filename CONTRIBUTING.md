# Contributing

Thanks for your interest in improving the 360° Character Viewer Toolkit.

## Ways to Contribute

### Report Issues
If something doesn't work as documented, open an issue with:
- Your prompt (or a summary of it)
- The error message or unexpected behavior
- What you expected to happen
- Your environment (OS, Python version, ffmpeg version)

### Share Your Results
Built something cool with this toolkit? Add it to `EXAMPLES.md` via pull request.

### Improve Documentation
Found a step that's confusing? Discovered a trick that works? Documentation PRs are always welcome.

### Extend the Viewer
The viewer is intentionally minimal (~60 lines of JS). If you build useful extensions (autoplay, zoom, comparison view, etc.), submit them as separate files in `viewer/extensions/` so the core stays lean.

## Pull Request Process

1. Fork the repo
2. Create a branch (`git checkout -b my-improvement`)
3. Make your changes
4. Test locally
5. Submit a PR with a clear description of what you changed and why

## Code Style

- Vanilla JavaScript only in the viewer (no frameworks, no build tools)
- Python scripts should work with Python 3.8+
- Keep it simple. The whole point of this toolkit is accessibility.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
