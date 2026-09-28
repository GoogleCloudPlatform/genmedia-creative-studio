# Developer's Guide

This document provides a detailed analysis of the Promptlandia codebase and offers recommendations for its improvement. It is intended for developers who want to contribute to the project.

## Codebase Analysis

The Promptlandia application is a well-structured web application built with the Mesop framework, complemented by a suite of command-line tools. It is organized into several directories, each with a specific purpose:

*   **`pages/`**: Each file in this directory defines a specific page within the web application. This separates the concerns of each view and makes the code easier to understand and maintain.
*   **`components/`**: This directory contains reusable UI components that are used throughout the application. This promotes code reuse and a consistent user interface.
*   **`state/`**: This directory manages the application's state using Mesop's state management capabilities. This is essential for a reactive web application.
*   **`config/`**: This directory handles the application's configuration, which is loaded from a `.env` file. This makes it easy to configure the application without modifying the code.
*   **`models/`**: This directory contains the logic for interacting with the generative AI model. It includes the prompts used for evaluation and improvement, as well as parsers for the model's output.
*   **`cli/`**: This directory contains command-line interface scripts (`trim.py`, `improve.py`, `checklist.py`) that expose the core functionality for terminal-based workflows.
*   **`tests/`**: This directory contains tests for the application. This is a good practice for ensuring code quality and maintainability.

## Key Features

Promptlandia offers several core tools for prompt engineering:

1.  **Prompt Improver:** Uses a "thinking" process to iteratively improve a prompt based on specific user instructions.
2.  **Prompt Health Check:** Evaluates a prompt against a comprehensive checklist of best practices.
3.  **Prompt Trimmer:** Reduces prompt size by removing generic LLM best practices while preserving core task-specific instructions. This is available both in the web UI and as a CLI tool.

## Planning & Methodology

This project uses the **Vibe Tasking** methodology for task management and AI-assisted development.

*   **Methodology:** We follow a structured approach using "Stories" and "AI Guides" to maintain context and ensure high-quality AI contributions.

*Note:* the Vibe Tasking framework files, roadmap and implementation plan are not
vendored into this repository; they are maintained outside it.

## Running the Application

### Web Interface
The application is built with the [Mesop](https://google.github.io/mesop/) framework.

1.  **Start the development server:**
    ```bash
    mesop app.py
    ```

### Command Line Interface (CLI)
For users who prefer the terminal or want to integrate Promptlandia into scripts, the `cli/` directory provides direct access to the tools.

**Prerequisites:** Ensure you have `uv` installed and your `.env` file configured.

**Examples:**

*   **Trim a prompt:**
    ```bash
    uv run cli/trim.py "Your verbose prompt here..."
    ```
*   **Improve a prompt:**
    ```bash
    uv run cli/improve.py -i "Make it shorter" "Write a story."
    ```
*   **Check prompt health:**
    ```bash
    uv run cli/checklist.py "My prompt"
    ```

For detailed usage instructions, refer to `cli/README.md`.

## Testing

The project uses Playwright for end-to-end testing. The tests are located in the `tests/` directory.

### Running the Tests

To run the tests, you will need to have the Mesop application running in one terminal:

```bash
mesop app.py
```

And in another terminal, you can run the Playwright tests using `pytest`:

```bash
pytest
```

### Writing New Tests

When adding new functionality to the application, it is important to also add corresponding end-to-end tests. Here are some guidelines for writing new tests:

*   **Create a new test file:** Create a new file in the `tests/` directory with a name that starts with `test_`.
*   **Write a test function:** Write a function that takes a `Page` object as an argument. The `Page` object is provided by Playwright and represents a single tab in a browser.
*   **Navigate to a page:** Use the `page.goto()` method to navigate to the page you want to test.
*   **Interact with the page:** Use the methods on the `Page` object to interact with the page, such as `page.get_by_label()`, `page.fill()`, and `page.click()`.
*   **Make assertions:** Use the `expect()` function from Playwright to make assertions about the state of the page.

## Future Improvements

The application is well-structured, but there are several areas where it could be improved to enhance its maintainability, readability, and overall quality. The following are some recommendations for improvement:

### 1. Architectural Enhancements
While the architecture is solid, the following suggestions could enhance it further, especially as the application grows in complexity.

*   **API Abstraction Layer:**
    *   **Suggestion:** To make the application even more model-agnostic, you could introduce a formal abstraction layer. Create a base class in `models/` (e.g., `LLMProvider`) with abstract methods like `generate_content` and `improve_prompt`. Then, have a `GeminiProvider` class that inherits from this base class and implements these methods.
    *   **Benefit:** This would allow you to switch between different LLM providers by simply changing which provider class is instantiated, adhering to the Strategy design pattern. This makes the system highly flexible and prepared for future changes in the AI landscape.

*   **Component Granularity:**
    *   **Suggestion:** Some of the `pages` files contain significant amounts of rendering logic (e.g., `checklist.py`). As these pages grow, consider breaking them down into smaller, more focused sub-components within their own directory (e.g., `pages/checklist/components/`).
    *   **Benefit:** This would make the page-level code cleaner and promote reusability of the sub-components, improving both maintainability and development speed.

*   **Error Handling:**
    *   **Suggestion:** The error handling in `models/gemini.py` currently uses a broad `except Exception`. It would be more robust to catch more specific exceptions from the `google.genai` library. You could also define custom application-level exceptions (e.g., `ModelGenerationError`) to be raised from the `models` layer and handled gracefully in the UI layer.
    *   **Benefit:** This would allow the UI to display more specific and helpful error messages to the user (e.g., "API key is invalid" vs. "An unknown error occurred").

*   **Configuration Management:**
    *   **Suggestion:** For managing settings, especially if you add more complex configurations like API keys or feature flags, consider using a library like `pydantic-settings`. It allows you to define your configuration as a Pydantic model and automatically loads settings from environment variables or `.env` files, providing type validation and error checking out of the box.
    *   **Benefit:** This makes your configuration more robust, self-documenting, and less error-prone.

### 2. Type Hinting

The code uses type hints, which is excellent. However, some of the type hints could be more specific. For example, in `pages/checklist.py`, the `details` field in the `CategoryData` class is typed as `Optional[Dict[str, Union[IssueDetail, str]]]`. It would be more precise to define a separate `TypedDict` for the `details` field to enforce a more specific structure.

### 3. Code Duplication

There is some code duplication in the `pages` directory. For example, the `gemini_prompt_input` component is defined in both `pages/generate.py` and `pages/checklist.py`. It would be better to move this component to the `components` directory to avoid duplication.

### 4. Logging

The application does not have any logging. It would be beneficial to add logging to the application to help with debugging and monitoring. The `logging` module in the Python standard library can be used for this purpose.

### 5. Docstrings

The docstrings in the code are good, but they could be more detailed. For example, the docstrings for the functions in the `gemini` module could include information about the exceptions that can be raised.

### 6. Code Formatting

The code is well-formatted, but it would be beneficial to use a code formatter, such as `black` or `ruff`, to ensure consistent formatting throughout the codebase.

### 7. Pre-commit Hooks

It would be beneficial to use pre-commit hooks to automatically run the code formatter and linter before each commit. This would help to ensure that the code is always well-formatted and free of linting errors.

By addressing these recommendations, the Promptlandia application can be made more robust, maintainable, and easier to contribute to.
