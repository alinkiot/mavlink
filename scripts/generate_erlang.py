#!/usr/bin/env python3
"""
MAVLink Erlang code generator.
Generates Erlang header file with record definitions and encode/decode functions.
"""

import xml.etree.ElementTree as ET
import sys
import os

def parse_type(field_type):
    """Convert MAVLink type to Erlang type."""
    type_map = {
        'uint8_t': 'integer(0..255)',
        'int8_t': 'integer(-128..127)',
        'uint16_t': 'integer(0..65535)',
        'int16_t': 'integer(-32768..32767)',
        'uint32_t': 'non_neg_integer',
        'int32_t': 'integer',
        'uint64_t': 'non_neg_integer',
        'int64_t': 'integer',
        'float': 'float',
        'double': 'float',
        'char': 'char()',  # 0-127
    }
    
    # Handle arrays
    if '[' in field_type:
        base_type = field_type.split('[')[0]
        return f'list({parse_type(base_type)})'
    
    return type_map.get(field_type, 'term()')

def generate_enum(enum_elem):
    """Generate Erlang enum definition."""
    name = enum_elem.get('name')
    entries = enum_elem.findall('entry')
    
    lines = [f'%% Enum: {name}']
    lines.append(f'-type {name.lower()}() ::')
    
    values = []
    for i, entry in enumerate(entries):
        entry_name = entry.get('name')
        value = entry.get('value')
        if i == 0:
            # First value
            values.append(f"    {entry_name.lower()}  %% {value}: {entry_name}")
        elif i == len(entries) - 1:
            # Last value
            values.append(f"  | {entry_name.lower()}.  %% {value}: {entry_name}")
        else:
            # Middle values
            values.append(f"  | {entry_name.lower()}  %% {value}: {entry_name}")
    
    if values:
        lines.append('\n'.join(values))
    else:
        lines.append('    term().')
    
    lines.append('')
    return '\n'.join(lines)

def generate_message(message_elem):
    """Generate Erlang record and functions for a message."""
    msg_id = message_elem.get('id')
    msg_name = message_elem.get('name')
    description = message_elem.find('description')
    
    lines = [f'%% Message: {msg_name} (ID: {msg_id})']
    if description is not None and description.text:
        lines.append(f'%% {description.text.strip()}')
    lines.append('')
    
    # Generate record
    fields = message_elem.findall('field')
    record_fields = []
    field_specs = []
    
    for field in fields:
        field_name = field.get('name').lower()
        field_type = field.get('type')
        field_enum = field.get('enum')
        field_units = field.get('units')
        field_desc = field.text if field.text else ''
        
        # Determine Erlang type
        if field_enum:
            erl_type = f'{field_enum.lower()}'
        else:
            erl_type = parse_type(field_type)
        
        record_fields.append(f'    {field_name} :: {erl_type}')
        field_specs.append({
            'name': field_name,
            'type': field_type,
            'enum': field_enum,
            'units': field_units
        })
    
    # Record definition
    lines.append(f'-record({msg_name.lower()}, {{')
    lines.append(',\n'.join(record_fields))
    lines.append('}).')
    lines.append('')
    
    # Type definition
    lines.append(f'-type {msg_name.lower()}() :: #{msg_name.lower()}{{}}.')
    lines.append('')
    
    # Message ID constant
    lines.append(f'-define({msg_name.upper()}_ID, {msg_id}).')
    lines.append('')
    
    # Encoder function
    lines.append(f'%% @doc Encode {msg_name} message to binary')
    lines.append(f'-spec encode_{msg_name.lower()}(#{msg_name.lower()}{{}}) -> binary().')
    lines.append(f'encode_{msg_name.lower()}(#{msg_name.lower()}{{')
    encode_fields = [f'    {f["name"]} = {f["name"]}' for f in field_specs]
    lines.append(',\n'.join(encode_fields))
    lines.append('}) ->')
    
    # Encoding logic
    encode_stmts = []
    for f in field_specs:
        fname = f['name']
        ftype = f['type']
        
        if '[' in ftype:
            # Array field
            base_type = ftype.split('[')[0]
            size = ftype.split('[')[1].rstrip(']')
            encode_stmts.append(f'    {fname}_binary = list_to_binary({fname}),')
        else:
            # Scalar field
            type_fmt = {
                'uint8_t': 'unsigned-integer-size(8)',
                'int8_t': 'signed-integer-size(8)',
                'uint16_t': 'unsigned-integer-size(16)',
                'int16_t': 'signed-integer-size(16)',
                'uint32_t': 'unsigned-integer-size(32)',
                'int32_t': 'signed-integer-size(32)',
                'uint64_t': 'unsigned-integer-size(64)',
                'int64_t': 'signed-integer-size(64)',
                'float': 'float',
                'double': 'float',
            }
            fmt = type_fmt.get(ftype, 'unsigned-integer-size(8)')
            encode_stmts.append(f'    {fname}_binary = <<{fname}/{fmt}>>,')
    
    lines.extend(encode_stmts)
    lines.append('    <<?MSG_ID:?MSG_ID_BITS, ' + 
                 ', '.join([f'{f["name"]}_binary/binary' for f in field_specs]) + '>>.')
    lines.append('')
    
    # Decoder function
    lines.append(f'%% @doc Decode binary to {msg_name} message')
    lines.append(f'-spec decode_{msg_name.lower()}(binary()) -> #{msg_name.lower()}{{}}.')
    lines.append(f'decode_{msg_name.lower()}(Binary) when is_binary(Binary) ->')
    
    # Decode pattern
    decode_pattern = '<<' + ', '.join([
        f'{f["name"]}/' + {
            'uint8_t': 'unsigned-8',
            'int8_t': 'signed-8',
            'uint16_t': 'unsigned-16',
            'int16_t': 'signed-16',
            'uint32_t': 'unsigned-32',
            'int32_t': 'signed-32',
            'uint64_t': 'unsigned-64',
            'int64_t': 'signed-64',
            'float': 'float',
            'double': 'float',
        }.get(f['type'], 'unsigned-8') for f in field_specs
    ]) + '>> = Binary,'
    
    lines.append(f'    {decode_pattern}')
    lines.append(f'    #{msg_name.lower()}{{')
    lines.append(',\n'.join([f'        {f["name"]} = {f["name"]}' for f in field_specs]))
    lines.append('    }.')
    lines.append('')
    
    return '\n'.join(lines)

def generate_header(xml_file, output_file, module_name):
    """Generate complete Erlang header file."""
    tree = ET.parse(xml_file)
    root = tree.getroot()
    
    # Header
    lines = [
        f'%% Automatically generated by generate_erlang.py',
        f'%% Source: {os.path.basename(xml_file)}',
        f'%% Do not edit manually!',
        '',
        f'-ifndef({module_name.upper()}_HRL).',
        f'-define({module_name.upper()}_HRL, true).',
        '',
        '%% MAVLink constants',
        '-define(MSG_ID_BITS, 8).',
        '-define(MSG_ID, 0).',
        '',
    ]
    
    # Generate enums
    enums = root.find('enums')
    if enums is not None:
        lines.append('%%====================================================================')
        lines.append('%% Enums')
        lines.append('%%====================================================================')
        lines.append('')
        for enum in enums.findall('enum'):
            lines.append(generate_enum(enum))
    
    # Generate messages
    messages = root.find('messages')
    if messages is not None:
        lines.append('%%====================================================================')
        lines.append('%% Messages')
        lines.append('%%====================================================================')
        lines.append('')
        for message in messages.findall('message'):
            lines.append(generate_message(message))
    
    lines.append('-endif. %% ' + module_name.upper() + '_HRL')
    
    # Write output
    with open(output_file, 'w') as f:
        f.write('\n'.join(lines))
    
    print(f'Generated {output_file}')

def main():
    if len(sys.argv) < 4:
        print(f'Usage: {sys.argv[0]} <input.xml> <output.hrl> <module_name>')
        print(f'Example: {sys.argv[0]} common.xml mavlink.hrl mavlink')
        sys.exit(1)
    
    xml_file = sys.argv[1]
    output_file = sys.argv[2]
    module_name = sys.argv[3]
    
    generate_header(xml_file, output_file, module_name)

if __name__ == '__main__':
    main()
