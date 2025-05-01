import pytest
from etabotapp.compression import (
    compress_payload,
    decompress_payload,
    decompress,
    SQS_MAX_SIZE_BYTES,
)

def test_compression_and_decompression_round_trip():
    original_data = {"key": "value", "numbers": list(range(100))}
    encoded = compress_payload(original_data, raise_sqs_max_size_error=True)
    decoded = decompress_payload(encoded)
    assert decoded == original_data

def test_compressed_message_under_limit():
    data = {"text": "a" * 1000}
    encoded = compress_payload(data, raise_sqs_max_size_error=True)
    assert len(encoded.encode("utf-8")) < SQS_MAX_SIZE_BYTES

def test_raises_error_when_payload_exceeds_limit():
    data = {"data": ["value_" + str(i) for i in range(100000)]}  # large and varied
    with pytest.raises(NameError):  # consider replacing NameError with a custom exception
        compress_payload(data, raise_sqs_max_size_error=True)

def test_decompress_decorator():
    called = {}

    @decompress
    def dummy_task(*args, **kwargs):
        print("Called with:", locals())  # prints all local variables (arguments)
        called["args"] = args
        called["kwargs"] = kwargs

    args_data = (1, 2, 3)
    kwargs_data = {"x": "y"}

    encoded_args = compress_payload(args_data, raise_sqs_max_size_error=True)
    encoded_kwargs = compress_payload(kwargs_data, raise_sqs_max_size_error=True)

    dummy_task(encoded_args, encoded_kwargs)

    assert called["args"] == args_data
    assert called["kwargs"] == kwargs_data
