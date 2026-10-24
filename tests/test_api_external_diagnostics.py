from tests.test_api_external import normalize_model_name


def test_normalize_model_name_accepts_bare_name_and_resource_name():
    assert normalize_model_name("text-embedding-004") == "text-embedding-004"
    assert (
        normalize_model_name("models/gemini-embedding-001")
        == "gemini-embedding-001"
    )
