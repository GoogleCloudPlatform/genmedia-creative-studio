# Running Tests

This directory contains the automated tests for the GenMedia Creative Studio application.

## Running All Tests

To run all tests, simply execute the following command from the root of the project:

```bash
pytest
```

## Running Individual Tests

To run a specific test file, simply pass the path to the file as an argument to the `pytest` command:

```bash
pytest test/test_identity.py
```

This is useful for focusing on a specific area of the application during development and debugging.

## Integration Tests

This suite includes integration tests that make real API calls to Google Cloud services. These tests are marked with the `integration` marker and are skipped by default to keep the standard test run fast and free of external dependencies.

To run only the integration tests, use the `-m` flag:

```bash
pytest -m integration -v -s
```

**Note:** These tests require valid Google Cloud authentication and will incur costs for the API calls made.

## Configuring the GCS Bucket

Several tests require access to Google Cloud Storage (GCS) to load test assets (e.g., images for VTO and Motion Portraits). To ensure these tests can run in different environments, the GCS bucket is configurable.

You can specify the GCS bucket to use with the `--gcs-bucket` command-line option. If you do not provide this option, the tests will default to using `gs://genai-blackbelt-fishfooding-assets`.

### Example

To run the tests using a custom GCS bucket, use the following command:

```bash
pytest --gcs-bucket gs://your-custom-test-bucket
```

This allows developers to use their own GCS resources without modifying the test code, making collaboration easier and more reliable.

## Standalone Tests

In addition to the `pytest` suite, this directory also contains standalone scripts for direct, simple testing of the VEO models:

-   `veo2_simple.py`: A script for testing the core functionalities of the Veo 2 model.
-   `veo3_simple.py`: A script for testing the core functionalities of the Veo 3 model.

These scripts can be run directly from the command line and are useful for quick, ad-hoc testing of the models without the overhead of the full test suite.
