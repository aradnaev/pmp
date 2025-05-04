import gzip
import base64
import json
from functools import wraps
import logging

logger = logging.getLogger(__name__)
SQS_MAX_SIZE_BYTES = 262144  # 256 KB

def compress_payload(data, raise_sqs_max_size_error: bool):
    json_data = json.dumps(data)
    raw_bytes = json_data.encode('utf-8')
    raw_size = len(raw_bytes)
    compressed = gzip.compress(json_data.encode('utf-8'))
    encoded = base64.b64encode(compressed).decode('utf-8')
    compressed_encoded_length = len(encoded.encode('utf-8'))
    gain = raw_size / compressed_encoded_length
    logger.info(
        f"Payload size: original={raw_size} bytes, "
        f"compressed={len(compressed)} bytes, "
        f"base64-encoded={compressed_encoded_length} bytes"
        f"compression gain={gain:.1f}x"
    )
    if raise_sqs_max_size_error and compressed_encoded_length > SQS_MAX_SIZE_BYTES:
        raise NameError(
            f"Compressed message exceeds SQS limit: {compressed_encoded_length} > {SQS_MAX_SIZE_BYTES} bytes"
        )
    return encoded

def decompress_payload(encoded):
    compressed = base64.b64decode(encoded.encode('utf-8'))
    json_data = gzip.decompress(compressed).decode('utf-8')
    return json.loads(json_data)

def decompress(func):
    @wraps(func)
    def wrapper(compressed_args, compressed_kwargs=None):
        args = decompress_payload(compressed_args)
        kwargs = decompress_payload(compressed_kwargs) if compressed_kwargs else {}
        return func(*args, **kwargs)
    return wrapper
