#!/usr/bin/env python3
"""
MAVLink Erlang encoder/decoder generator.
Generates encode/decode functions for all MAVLink messages.
Compatible with Erlang/OTP 24+
"""

import xml.etree.ElementTree as ET
import sys
import os

# MAVLink type to Erlang binary format mapping
TYPE_MAP = {
    'uint8_t': ('unsigned-integer', 8),
    'int8_t': ('signed-integer', 8),
    'uint16_t': ('unsigned-integer', 16),
    'int16_t': ('signed-integer', 16),
    'uint32_t': ('unsigned-integer', 32),
    'int32_t': ('signed-integer', 32),
    'uint64_t': ('unsigned-integer', 64),
    'int64_t': ('signed-integer', 64),
    'float': ('float', 32),
    'double': ('float', 64),
    'char': ('binary', 8),
}

def get_erlang_type(mavlink_type):
    """Convert MAVLink type to Erlang binary format spec."""
    # Handle array types
    if '[' in mavlink_type:
        base_type = mavlink_type.split('[')[0]
        size = mavlink_type.split('[')[1].split(']')[0]
        return ('array', base_type, int(size))
    
    # Handle simple types
    if mavlink_type in TYPE_MAP:
        return TYPE_MAP[mavlink_type]
    
    # Default to uint8_t
    return ('unsigned-integer', 8)

def generate_encoder(message_elem):
    """Generate encoder function for a message."""
    msg_id = message_elem.get('id')
    msg_name = message_elem.get('name')
    msg_name_lower = msg_name.lower()
    
    fields = message_elem.findall('field')
    
    lines = []
    lines.append(f'%% @doc Encode {msg_name} message to binary')
    lines.append(f'-spec encode_{msg_name_lower}(#{msg_name_lower}{{}}) -> binary().')
    lines.append(f'encode_{msg_name_lower}(#{msg_name_lower}{{')
    
    # Generate field extraction
    field_extractions = []
    field_mappings = []
    for field in fields:
        field_name = field.get('name').lower()
        field_type = field.get('type')
        
        # Handle reserved words
        reserved_words = {'end', 'begin', 'after', 'catch', 'case', 'fun', 'if', 'of', 'receive', 'try', 'when'}
        if field_name in reserved_words:
            field_name_orig = field_name
            field_name = field_name + '_'
        else:
            field_name_orig = field_name
        
        # Variable name must start with uppercase in Erlang
        var_name = ''.join(word.capitalize() for word in field_name.split('_'))
        field_extractions.append(f'    {field_name} = {var_name}')
        field_mappings.append((field_name, var_name, field_type))
    
    lines.append(',\n'.join(field_extractions))
    lines.append('}) ->')
    
    # Check if message ID fits in 8 bits (MAVLink 2.0 supports 16-bit IDs)
    msg_id_int = int(msg_id)
    if msg_id_int > 255:
        # Use 16-bit message ID for MAVLink 2.0 extended messages
        binary_parts = [f'    <<?{msg_name}_ID:16/little-unsigned-integer']
    else:
        # Use 8-bit message ID for standard MAVLink messages
        binary_parts = [f'    <<?{msg_name}_ID:8']
    
    for field_name, var_name, field_type in field_mappings:
        erl_type = get_erlang_type(field_type)
        
        if erl_type[0] == 'array':
            # Handle arrays
            base_type, array_size = erl_type[1], erl_type[2]
            base_erl = TYPE_MAP.get(base_type, ('unsigned-integer', 8))
            binary_parts.append(f'      {var_name}:{base_erl[1]}/little-{base_erl[0]}')
        else:
            # Handle simple types
            binary_parts.append(f'      {var_name}:{erl_type[1]}/little-{erl_type[0]}')
    
    lines.append(',\n'.join(binary_parts) + '>>.')
    lines.append('')
    
    return '\n'.join(lines)

def generate_decoder(message_elem):
    """Generate decoder function for a message."""
    msg_id = message_elem.get('id')
    msg_name = message_elem.get('name')
    msg_name_lower = msg_name.lower()
    
    fields = message_elem.findall('field')
    
    lines = []
    lines.append(f'%% @doc Decode {msg_name} message from binary')
    lines.append(f'-spec decode_{msg_name_lower}(binary()) -> #{msg_name_lower}{{}}.')
    
    # Check if message ID fits in 8 bits
    msg_id_int = int(msg_id)
    if msg_id_int > 255:
        # Use 16-bit message ID for MAVLink 2.0 extended messages
        lines.append(f'decode_{msg_name_lower}(<<?{msg_name}_ID:16/little-unsigned-integer,')
    else:
        # Use 8-bit message ID for standard MAVLink messages
        lines.append(f'decode_{msg_name_lower}(<<?{msg_name}_ID:8,')
    
    # Generate binary pattern matching
    binary_parts = []
    field_mappings = []
    for field in fields:
        field_name = field.get('name').lower()
        field_type = field.get('type')
        
        erl_type = get_erlang_type(field_type)
        
        # Variable name must start with uppercase in Erlang
        var_name = ''.join(word.capitalize() for word in field_name.split('_'))
        
        if erl_type[0] == 'array':
            base_type, array_size = erl_type[1], erl_type[2]
            base_erl = TYPE_MAP.get(base_type, ('unsigned-integer', 8))
            binary_parts.append(f'                   {var_name}:{base_erl[1]}/little-{base_erl[0]}')
        else:
            binary_parts.append(f'                   {var_name}:{erl_type[1]}/little-{erl_type[0]}')
        
        # Handle reserved words
        reserved_words = {'end', 'begin', 'after', 'catch', 'case', 'fun', 'if', 'of', 'receive', 'try', 'when'}
        if field_name in reserved_words:
            field_name = field_name + '_'
        
        field_mappings.append((field_name, var_name))
    
    lines.append(',\n'.join(binary_parts) + '>>) ->')
    
    # Generate record construction
    lines.append(f'    #{msg_name_lower}{{')
    
    record_fields = []
    for field_name, var_name in field_mappings:
        record_fields.append(f'        {field_name} = {var_name}')
    
    lines.append(',\n'.join(record_fields))
    lines.append('    }.')
    lines.append('')
    
    return '\n'.join(lines)

def generate_codec_module(xml_file, output_file, module_name, header_file):
    """Generate complete encoder/decoder module."""
    tree = ET.parse(xml_file)
    root = tree.getroot()
    
    messages = root.find('messages')
    if messages is None:
        return
    
    lines = []
    
    # Module header
    lines.append(f'-module({module_name}_codec).')
    lines.append(f'-include("{header_file}").')
    lines.append('')
    lines.append('%% API')
    lines.append('-export([')
    
    # Generate export list
    exports = []
    for message in messages.findall('message'):
        msg_name_lower = message.get('name').lower()
        exports.append(f'    encode_{msg_name_lower}/1')
        exports.append(f'    decode_{msg_name_lower}/1')
    
    lines.append(',\n'.join(exports))
    lines.append(']).')
    lines.append('')
    
    # Generate encode/decode functions for each message
    for message in messages.findall('message'):
        lines.append(generate_encoder(message))
        lines.append(generate_decoder(message))
    
    # Write output
    with open(output_file, 'w') as f:
        f.write('\n'.join(lines))
    
    print(f'✓ Generated {output_file}')
    print(f'  - Functions: {len(messages.findall("message")) * 2}')

def main():
    if len(sys.argv) < 5:
        print(f'Usage: {sys.argv[0]} <input.xml> <output.erl> <module_name> <header_file>')
        print(f'Example: {sys.argv[0]} common.xml mavlink_common_codec.erl mavlink_common mavlink_common.hrl')
        sys.exit(1)
    
    xml_file = sys.argv[1]
    output_file = sys.argv[2]
    module_name = sys.argv[3]
    header_file = sys.argv[4]
    
    generate_codec_module(xml_file, output_file, module_name, header_file)

if __name__ == '__main__':
    main()
