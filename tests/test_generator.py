from unittest.mock import patch

from content_generator import generate_post


def test_generate_post_with_examples():
    with patch("content_generator._get_client") as mock_client:
        mock_client.return_value.chat.completions.create.return_value = type(
            "Resp",
            (),
            {
                "choices": [
                    type(
                        "Choice",
                        (),
                        {
                            "message": type(
                                "Message",
                                (),
                                {"content": "Mocked generated post."},
                            )
                        },
                    )
                ]
            },
        )
        result = generate_post(["Example one", "Example two"], company_name="Acme")
        assert result == "Mocked generated post."
        mock_client.return_value.chat.completions.create.assert_called_once()


def test_generate_post_without_examples():
    with patch("content_generator._get_client") as mock_client:
        mock_client.return_value.chat.completions.create.return_value = type(
            "Resp",
            (),
            {
                "choices": [
                    type(
                        "Choice",
                        (),
                        {
                            "message": type(
                                "Message",
                                (),
                                {"content": "Context-only post."},
                            )
                        },
                    )
                ]
            },
        )
        result = generate_post([])
        assert result == "Context-only post."


def test_generate_post_missing_key():
    with patch(
        "content_generator._get_client", side_effect=RuntimeError("missing key")
    ):
        try:
            generate_post([])
        except RuntimeError as e:
            assert "missing key" in str(e)
