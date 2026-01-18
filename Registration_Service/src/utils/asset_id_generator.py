#!/usr/bin/env python3
"""
Asset ID Generator Utility

Generates base64-encoded UUIDs for use as globalAssetId values in AAS configurations.

Usage:
    # Generate a new globalAssetId
    python asset_id_generator.py generate
    
    # Generate multiple IDs
    python asset_id_generator.py generate --count 5
    
    # Decode an existing base64 ID
    python asset_id_generator.py decode NGQ5ZWE4ZmUtY2Q3OS00Nzc5LWE5YjEtNGEzZGRkODRhNzQ2
    
    # Generate with custom base URL
    python asset_id_generator.py generate --base-url https://example.com/assets
"""

import argparse
import base64
import uuid
import sys
from typing import Optional


DEFAULT_BASE_URL = "https://smartproductionlab.aau.dk/assets"


def generate_asset_id() -> str:
    """
    Generate a new UUID for use as an asset identifier.

    Returns:
        A new UUID string (e.g., '4d9ea8fe-cd79-4779-a9b1-4a3ddd84a746')
    """
    return str(uuid.uuid4())


def encode_to_base64(value: str) -> str:
    """
    Encode a string to base64.

    Args:
        value: String to encode (typically a UUID)

    Returns:
        Base64-encoded string
    """
    return base64.b64encode(value.encode('utf-8')).decode('utf-8')


def decode_from_base64(encoded: str) -> str:
    """
    Decode a base64 string.

    Args:
        encoded: Base64-encoded string

    Returns:
        Decoded string (typically a UUID)
    """
    return base64.b64decode(encoded).decode('utf-8')


def generate_global_asset_id(base_url: str = DEFAULT_BASE_URL) -> tuple[str, str, str]:
    """
    Generate a complete globalAssetId URL with a new UUID.

    Args:
        base_url: Base URL for the asset (default: smartproductionlab.aau.dk/assets)

    Returns:
        Tuple of (full_url, base64_encoded, uuid_string)
    """
    new_uuid = generate_asset_id()
    encoded = encode_to_base64(new_uuid)
    full_url = f"{base_url}/{encoded}"
    return full_url, encoded, new_uuid


def decode_global_asset_id(url_or_encoded: str) -> dict:
    """
    Decode a globalAssetId URL or base64 string to reveal the UUID.

    Args:
        url_or_encoded: Either a full URL or just the base64-encoded portion

    Returns:
        Dictionary with 'encoded', 'decoded', and 'is_valid_uuid' keys
    """
    # Extract base64 portion if it's a URL
    if url_or_encoded.startswith('http'):
        encoded = url_or_encoded.rsplit('/', 1)[-1]
    else:
        encoded = url_or_encoded

    try:
        decoded = decode_from_base64(encoded)
        # Check if it's a valid UUID format
        try:
            uuid.UUID(decoded)
            is_valid_uuid = True
        except ValueError:
            is_valid_uuid = False

        return {
            'encoded': encoded,
            'decoded': decoded,
            'is_valid_uuid': is_valid_uuid
        }
    except Exception as e:
        return {
            'encoded': encoded,
            'decoded': None,
            'error': str(e),
            'is_valid_uuid': False
        }


def main():
    parser = argparse.ArgumentParser(
        description='Generate and decode base64-encoded UUIDs for AAS globalAssetId values',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s generate                          Generate a new globalAssetId
  %(prog)s generate --count 3                Generate 3 new globalAssetIds
  %(prog)s generate --uuid-only              Output only the base64 string
  %(prog)s decode NGQ5ZWE4ZmUtY2Q3OS00...    Decode a base64 string to UUID
  %(prog)s decode https://smartproductionlab.aau.dk/assets/NGQ5ZWE4...  Decode from URL
        """
    )

    subparsers = parser.add_subparsers(
        dest='command', help='Available commands')

    # Generate command
    gen_parser = subparsers.add_parser(
        'generate', help='Generate new globalAssetId(s)')
    gen_parser.add_argument(
        '--count', '-n',
        type=int,
        default=1,
        help='Number of IDs to generate (default: 1)'
    )
    gen_parser.add_argument(
        '--base-url', '-b',
        type=str,
        default=DEFAULT_BASE_URL,
        help=f'Base URL for the asset (default: {DEFAULT_BASE_URL})'
    )
    gen_parser.add_argument(
        '--uuid-only', '-u',
        action='store_true',
        help='Output only the base64-encoded UUID (for direct use in YAML)'
    )
    gen_parser.add_argument(
        '--yaml', '-y',
        action='store_true',
        help='Output in YAML format ready to paste'
    )

    # Decode command
    dec_parser = subparsers.add_parser(
        'decode', help='Decode a base64 globalAssetId')
    dec_parser.add_argument(
        'value',
        type=str,
        help='Base64-encoded string or full globalAssetId URL to decode'
    )

    args = parser.parse_args()

    if args.command == 'generate':
        for i in range(args.count):
            full_url, encoded, new_uuid = generate_global_asset_id(
                args.base_url)

            if args.uuid_only:
                print(encoded)
            elif args.yaml:
                print(f"    globalAssetId: '{full_url}'")
            else:
                if args.count > 1:
                    print(f"\n--- ID {i + 1} ---")
                print(f"UUID:        {new_uuid}")
                print(f"Base64:      {encoded}")
                print(f"Full URL:    {full_url}")

    elif args.command == 'decode':
        result = decode_global_asset_id(args.value)

        if 'error' in result:
            print(f"Error decoding: {result['error']}", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Encoded:     {result['encoded']}")
            print(f"Decoded:     {result['decoded']}")
            print(f"Valid UUID:  {'Yes' if result['is_valid_uuid'] else 'No'}")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
