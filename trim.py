import subprocess
import json
from base64 import b64decode
import zlib
from GlyphModder import write_metadata
import os

def read_meta(filename):
    b64_padding = '=='
    ffprobe_json = json.loads(subprocess.check_output(['ffprobe', '-v', 'quiet', '-of', 'json', '-show_streams', '-select_streams', 'a:0', filename]).decode('utf-8'))

    try:
        author = str(ffprobe_json['streams'][0]['tags']['AUTHOR'])
        custom1 = str(ffprobe_json['streams'][0]['tags']['CUSTOM1'])
    except KeyError:
        return
    
    author = b64decode(author + b64_padding)
    custom1 = b64decode(custom1 + b64_padding)

    author = zlib.decompress(author)
    custom1 = zlib.decompress(custom1)

    return author.decode(), custom1.decode()


def gc1_decode(gc):
    ret = []
    for c in gc:
        ret.append([int(c.split('-')[0]), int(c.split('-')[1])])
    return ret

def gc1_encode(gc):
    ret = []
    for c in gc:
        ret.append(f"{c[0]}-{c[1]}")
    return ','.join(ret) + ','

def list_encode(l):
    return [c.encode() for c in l]

def trim_ringtone(filename, author, custom, ss, to, temp_filename):
    tick_ss = int(ss * 1000 // 16)
    tick_to = int(to * 1000 // 16)
    ms_ss = int(ss * 1000)
    ms_to = int(to * 1000)

    author = author.split('\n')[:-1]
    custom = gc1_decode(custom.split(',')[:-1])
    ret_gc = []

    for c in range(len(custom)):
        custom[c][0] -= ms_ss
        if custom[c][0] > 0 and custom[c][0] < (ms_to - ms_ss):
            ret_gc.append(custom[c])
    
    author = author[tick_ss:tick_to]
    custom = gc1_encode(ret_gc)

    code = subprocess.run(['ffmpeg', '-y', '-v', 'quiet', '-i', filename, '-strict', '-2', '-c:a', 'opus', '-map_metadata', '0:s:a:0', '-ss', str(ss), '-to', str(to), f'{temp_filename}.ogg'])
    open(f'{temp_filename}.glypha', 'wb').write(b'\r\n'.join(list_encode(author)) + b'\r\n')
    open(f'{temp_filename}.glyphc1', 'wb').write(custom.encode())
    write_metadata(f'{temp_filename}.ogg', f'{temp_filename}.glypha', f'{temp_filename}.glyphc1', 'MyCustomSong', 'ffmpeg')
    os.remove(filename)
    os.remove(f'{temp_filename}.glypha')
    os.remove(f'{temp_filename}.glyphc1')
    os.rename(f'{temp_filename}.ogg', filename)


# author, custom = read_meta('tato.ogg')
# trim_ringtone('tato.ogg', author, custom, 1, 10.5)