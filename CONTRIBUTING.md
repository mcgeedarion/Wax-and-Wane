# Contributing to Wax and Wane

Thank you for your interest in contributing to Wax and Wane! This document provides guidelines and instructions for contributors.

## Development Setup

### Prerequisites

- **macOS** (required for testing brightness control)
- **Swift 5.9+** (for native implementation)
- **Python 3.10+** (for reference implementation)
- **Homebrew** (for installing dependencies)

### Installing Dependencies

```bash
# Install Swift dependencies
brew install kbrightness brightness ddcctl

# Install Python dependencies
pip install opencv-python numpy pytest
```

### Running Tests

```bash
# Run all tests
make test

# Run Python tests only
python -m pytest python/Tests

# Run Swift tests only
cd swift && swift test
```

### Code Style

#### Python
- Follow PEP 8 style guidelines
- Use type hints for function signatures
- Write docstrings for public functions and classes
- Maximum line length: 100 characters

```bash
# Lint Python code
python -m py_compile python/Sources/*.py
```

#### Swift
- Follow Swift API Design Guidelines
- Use meaningful variable and function names
- Document public APIs with DocC comments

## Project Structure

```
wax-and-wane/
├── swift/              # Native Swift implementation (production)
│   ├── Sources/
│   └── Tests/
├── python/             # Reference Python implementation
│   ├── Sources/
│   │   ├── settings.py    # Configuration handling
│   │   ├── policy.py      # Brightness calculation logic
│   │   ├── backends.py    # Hardware backend interfaces
│   │   ├── camera.py      # Webcam capture
│   │   └── cli.py         # CLI and main loop
│   └── Tests/
├── .github/workflows/  # CI/CD configuration
└── examples/           # Example configurations
```

## Making Contributions

### Reporting Bugs

1. Check existing issues first
2. Include:
   - macOS version
   - Wax and Wane version
   - Steps to reproduce
   - Expected vs actual behavior
   - Relevant logs

### Submitting Changes

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Add/update tests as needed
5. Ensure all tests pass
6. Update documentation if needed
7. Submit a pull request

### Pull Request Guidelines

- Keep PRs focused on a single concern
- Write clear commit messages
- Include tests for new functionality
- Update CHANGELOG.md for user-facing changes
- Be responsive to code review feedback

## Testing Requirements

### Unit Tests
- Test pure functions in isolation
- Mock external dependencies (camera, backends)
- Cover edge cases and error conditions

### Integration Tests
- Test full workflow from config to output
- Verify interaction between components

### Manual Testing
- Test on real hardware when possible
- Verify brightness changes are smooth
- Test with different ambient light conditions

## Security Considerations

- Never execute untrusted code or paths
- Validate all input configuration
- Use trusted directories for executables only
- Follow principle of least privilege

## Release Process

1. Update version in `swift/Sources/wax-and-wane/main.swift`
2. Update CHANGELOG.md
3. Create release tag
4. Build and sign binaries
5. Publish release notes

## Questions?

Open an issue for questions or discussions about contributions.
