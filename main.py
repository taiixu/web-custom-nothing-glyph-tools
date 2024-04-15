from flask import Flask, request, make_response, send_file
import os
from base64 import b64encode
import struct
import time
import string
import subprocess
import threading
import scipy.io.wavfile
import numpy as np

from GlyphTranslator import convert_label
from GlyphModder import write_meta

import GlyphV1 as glyph1
import GlyphV2 as glyph2

import trim as trimmer

COOKIE_ALLOWED_CHARS = string.ascii_letters + string.digits
MAX_COOKIE_LENGTH = 75
MIN_COOKIE_LENGTH = 24
REQUEST_DELAY = 5
MAX_SIZE = 1000 * 1024 * 10
DELETE_TIMEOUT = 60 * 20
THREAD_UPDATE = 15
URL = 'http://localhost'

# temp_db = {} # is used to store IP addresses and server access times
app = Flask(__name__)


def gen_cookie():
    '''
    Generates a cookie

    Cookies has two parts: time and random bytes
    Cookies are base64 encrypted and characters such as: = / + have been removed
    '''

    part1 = b64encode(struct.pack('>d', time.time())).decode().replace('=', '').replace('/', '').replace('+', '')
    part2 = b64encode(os.urandom(24)).decode().replace('=', '').replace('+', '').replace('/', '')
    return part1 + part2


def check_cookies(cookie):
    '''
    Checks if the cookie has a illegal characters

    Returns True if illegal characters has been founded
    Returns False if cookies is valid
    '''

    for c in cookie:
        if c not in COOKIE_ALLOWED_CHARS:
            return True
    return False


def remove_extension(filename):
    '''
    Removes extension from filename

    test.txt -> test
    '''

    return '.'.join(filename.split('.')[:-1])


def json_to_html(j):
    '''
    Converts the json message to html

    {'type': 'info', 'message': 'test', 'color': 'green'} -> <span class="c-green">test</span><br>
    '''

    ret = ''
    for c in j:
        ret += '<span class="c-' + c['color'] + '">' + c['message'] + '</span><br>\n'
    return ret


def safe_check(req):
    '''
    Checks that the request is safe
    '''

    # if temp_db.get(req.remote_addr) == None:
    #     temp_db.update({req.remote_addr: time.time()})
    # elif time.time() - temp_db.get(req.remote_addr) <= REQUEST_DELAY:
    #     return {'error': True, 'message': 'Please wait ' + str(REQUEST_DELAY) + ' seconds'}
    # else:
    #     temp_db.update({req.remote_addr: time.time()})
    
    if req.cookies.get('id') == None:
        return {'error': True, 'message': 'Error: refresh page to get cookies'}
    elif check_cookies(req.cookies.get('id')):
        return {'error': True, 'message': 'Error: found a banned letter in your cookies'}
    elif len(req.cookies.get('id')) > MAX_COOKIE_LENGTH:
        return {'error': True, 'message': 'Error: cookies cant be that long'}
    elif len(req.cookies.get('id')) < MIN_COOKIE_LENGTH:
        return {'error': True, 'message': 'Error: cookies cant be that short'}
    return False


@app.route('/api/glyph', methods=['GET', 'POST'])
def glyph():
    s = safe_check(request)
    if s:
        return s
    
    if request.method == 'POST':
        time_now = int(time.time())
        audio = request.files['audio']
        label = request.files['label']
        audio_extension = audio.filename.split('.')[-1]
        audio_filename = f"{request.cookies.get('id')}.{time_now}.{audio_extension}"
        audio_filename_e = f"{request.cookies.get('id')}.{time_now}"
        label_filename = f"{request.cookies.get('id')}.{time_now}.txt"
        label_filename_e = f"{request.cookies.get('id')}.{time_now}"
        audio.save(f'temp-files/{audio_filename}')
        label.save(f'temp-files/{label_filename}')
        if audio_extension != 'ogg':
            code = subprocess.call(['ffmpeg', '-y', '-v', 'quiet', '-i', f'temp-files/{audio_filename}', '-strict', '-2', '-c:a', 'opus', '-map_metadata', '0:s:a:0', f'temp-files/{audio_filename_e}.ogg'])
            if code != 0:
                return {'error': True, 'message': 'Error: converting audio error'}
        t_msg = convert_label(f"temp-files/{label_filename}")
        m_msg = write_meta(f"temp-files/{audio_filename_e}.ogg", f"temp-files/{label_filename_e}.glypha", f"temp-files/{label_filename_e}.glyphc1")
        return {
            'error': False,
            'content': {
                't_msg': json_to_html(t_msg),
                'm_msg': json_to_html(m_msg)
            },
            'files': {
                'audio': f"{URL}/api/getfile/{audio_filename_e}.ogg",
                'glypha': f"{URL}/api/getfile/{remove_extension(label_filename)}.glypha",
                'glyphc1': f"{URL}/api/getfile/{remove_extension(label_filename)}.glyphc1"
            }
        }
    

@app.route('/api/osu/upload', methods=['POST'])
def osu_upload():
    s = safe_check(request)
    if s:
        return s
    
    time_now = int(time.time())
    beatmap = request.files['beatmap']
    beatmap_name = f"{request.cookies.get('id')}.{time_now}.osz"
    beatmap.save(f"temp-files/{beatmap_name}")
    try:
        beatmap_info = glyph2.beatmap_info(beatmap_name)
    except:
        return {'error': True, 'message': 'Error: This file is not osu beatmapset'}

    r = make_response({
        'error': False,
        'content': beatmap_info
    })
    r.set_cookie('t', str(time_now))
    return r


@app.route('/api/osu', methods=['GET'])
def osu():
    s = safe_check(request)
    if s:
        return s
    
    filename = f"{request.cookies.get('id')}.{request.cookies.get('t')}"
    args = request.args
    try:
        ver = args.get('ver')
        map_n = args.get('n')
        seed = int(args.get('seed'))
        note_size = int(args.get('ns'))
        is_np2 = args.get('np2')
    except:
        return {'error': True, 'message': 'Error: Incorrect parameters (check the note size and seed fields, only numbers should be written in them)'}
    
    g = glyph1 if ver == 'v1' else glyph2
    
    try:
        map = g.get_map_w(f"{filename}.osz", int(map_n))
    except:
        return {'error': True, 'message': 'Error: Upload your file'}
    
    try:
        audio_filename = g.get_audio(f"{filename}.osz", int(map_n), filename)
    except:
        return {'error': True, 'message': 'Error: Unzipping beatmapset error'}
    
    code = subprocess.call(['ffmpeg', '-y', '-v', 'quiet', '-i', f'{audio_filename}', '-strict', '-2', '-c:a', 'opus', '-map_metadata', '0:s:a:0', f'temp-files/{filename}.c.ogg'])
    if code != 0:
        return {'error': True, 'message': 'Error: audio converting error'}
    converted_file = f"{filename}.c.ogg"
    if ver == 'v1':
        msg, label = g.conv(map, int(note_size))
    elif ver == 'v2':
        np = 'np2' if is_np2 == 'true' else 'np1'
        msg, label = g.conv(map, int(note_size), int(seed), np)
    open(f"temp-files/{filename}.txt", 'w').write('\n'.join(label) + '\n')

    t_msg = convert_label(f"temp-files/{filename}.txt")
    m_msg = write_meta(f"temp-files/{converted_file}", f"temp-files/{filename}.glypha", f"temp-files/{filename}.glyphc1")

    return {
        'error': False,
        'content': {
            'msg': json_to_html(msg),
            't_msg': json_to_html(t_msg),
            'm_msg': json_to_html(m_msg)
        },
        'files': {
            'audio': f'{URL}/api/getfile/{converted_file}',
            'label': f'{URL}/api/getfile/{filename}.txt',
            'glypha': f'{URL}/api/getfile/{filename}.glypha',
            "glyphc1": f'{URL}/api/getfile/{filename}.glyphc1'
        }
    }


@app.route('/api/getfile/<filename>')
def getfile(filename):
    f_name = 'audio' if filename.split('.')[-1] == 'ogg' else 'label'
    return send_file(f'temp-files/{filename}', download_name=f"{f_name}.{filename.split('.')[-1]}")


@app.route('/api/trim/upload', methods=['POST'])
def trim_upload():
    s = safe_check(request)
    if s:
        return s
    
    time_now = int(time.time())
    file = request.files['audio']
    if file.filename.split('.')[-1] != 'ogg':
        r = make_response({
            'error': True,
            'message': 'Error: only ogg files are supported for uploading'
        })
        return r
    
    filename = f"{request.cookies.get('id')}.{time_now}.ogg"
    file.save(f"temp-files/{filename}")
    wav_filepath = f"temp-files/{time.time()}.wav"
    code = subprocess.call(['ffmpeg', '-y', '-v', 'quiet', '-i', f"temp-files/{filename}", '-acodec', 'pcm_f32le', wav_filepath])
    if code != 0:
        r = make_response({
            'error': True,
            'message': 'Error: ffmpeg error'
        })
        return r

    samplerate, data = scipy.io.wavfile.read(wav_filepath)
    duration = len(data) / samplerate
    os.remove(wav_filepath)
    if len(data) % 100 != 0:
        data = data[:-(len(data) % 100)]
    arrays = np.split(data, 100)
    avg = []
    for c in arrays:
        avg.append(np.sqrt(np.mean(np.abs(c) ** 2)))
    m = max(avg)
    avg_final = []
    for c in avg:
        avg_final.append(float(c / m))
    
    try:
        author_parsed = []
        custom_parsed = []
        author, custom = trimmer.read_meta(f'temp-files/{filename}')
        author = author.split('\r\n')[:-1]
        custom = custom.split(',')[:-1]
        for c in author:
            author_parsed.append(','.join(c.split(',')[:-1]))
        for c in custom:
            custom_parsed.append([int(c.split('-')[0]) / (duration * 1000), int(c.split('-')[1])])
    except:
        return {'error': True, 'message': 'Error: It is not nothing ringtone'}
    
    r = make_response({
        'error': False, 
        'url': f"{URL}/api/getfile/{filename}",
        'peaks': avg_final,
        'author': author_parsed,
        'custom': custom_parsed,
        'duration': duration
    })
    r.set_cookie('t', str(time_now))
    return r


@app.route('/api/trim')
def trim():
    s = safe_check(request)
    if s:
        return s
    ss = request.args.get('ss')
    to = request.args.get('to')
    if ss == None or to == None:
        return {'error': True, 'message': 'Error: missing required arguments (ss, to)'}
    filename = f"{request.cookies.get('id')}.{request.cookies.get('t')}"
    author, custom = trimmer.read_meta(f'temp-files/{filename}.ogg')
    trimmer.trim_ringtone(f"temp-files/{filename}.ogg", author, custom, float(ss), float(to), f"temp-files/temp_{filename}")
    return {
        'error': False,
        'file': f"{URL}/api/getfile/{filename}.ogg"
    }


@app.route('/api/getcookies')
def cookies():
    r = make_response({'error': False})
    r.set_cookie('id', gen_cookie())
    return r


def del_files_thread():
    while True:
        filelist = os.listdir('temp-files/')
        for c in filelist:
            try:
                t = int(c.split('.')[-2])
            except:
                t = int(c.split('.')[-3])
            if t + DELETE_TIMEOUT < time.time():
                try:
                    os.remove(f'temp-files/{c}')
                except:
                    continue
                print(f"Removed: {c}")
        time.sleep(THREAD_UPDATE)

t = threading.Thread(target=del_files_thread, daemon=True).start()