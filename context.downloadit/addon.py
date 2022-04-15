#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import xbmc
import xbmcaddon
import xbmcgui,xbmcvfs
import time
import re, string
import json
import operator
from fractions import Fraction

addon = xbmcaddon.Addon()    
translation = addon.getLocalizedString
folder = addon.getSetting("folder")
bg = addon.getSetting('bg') == 'true'
ffmpgfile = addon.getSetting("ffmpgfile")
ffprobefile = addon.getSetting("ffprobefile")
askstreams = addon.getSetting("askstreams") == 'true'
askurl = addon.getSetting("askurl") == 'true'
warning = addon.getSetting("warning")
lastffmpg = addon.getSetting("lastffmpg")

if sys.version_info.major >= 3:
	fsencoding = sys.getfilesystemencoding()
	if fsencoding == 'ascii': fsencoding = 'utf-8'

	def fsenc(string):
		return string.encode(fsencoding)
else:
	def fsenc(string):
		return string

def copycase(a, b):
	if b.islower(): return a.lower()
	elif b.isupper(): return a.upper()
	elif b.istitle(): return a.title()
	else: return a

def ffmpeg2ffprobe(ffmpeg):
	return re.sub(r'(?<=ff)mpeg',
	  (lambda mpeg: copycase('probe', mpeg.group())),
	  ffmpeg, flags = re.IGNORECASE)

if lastffmpg != ffmpgfile:
	newffprobe = ffmpeg2ffprobe(ffmpgfile)
	if newffprobe != ffmpgfile and newffprobe != ffprobefile and \
	  os.path.exists(newffprobe):
		if xbmcgui.Dialog().yesno(translation(30013),
		  translation(30014).format(old=ffprobefile, new=newffprobe)):
			ffprobefile = newffprobe
			addon.setSetting('ffprobefile', ffprobefile)
	addon.setSetting('lastffmpg', ffmpgfile)

def debug(content):
    log(content, xbmc.LOGDEBUG)
    
def notice(content):
    log(content, xbmc.LOGINFO)

def log(msg, level=xbmc.LOGINFO):
    addon = xbmcaddon.Addon()
    addonID = addon.getAddonInfo('id')
    xbmc.log('%s: %s' % (addonID, msg), level) 

def downloadyoutube(file,ffdir=""):
 import YDStreamUtils
 import YDStreamExtractor

 debug("Start downloadyoutube")
 # if FFmpeg is defined use it also at youtube-dl
 if not ffdir=="": 
    YDStreamExtractor.overrideParam('ffmpeg_location',ffdir)
 
 # download video
 YDStreamExtractor.overrideParam('preferedformat',"avi")  
 vid = YDStreamExtractor.getVideoInfo(file,quality=2)  
 with YDStreamUtils.DownloadProgress() as prog: # this creates a progress dialog interface ready to use
    try:
        YDStreamExtractor.setOutputCallback(prog)
        result = YDStreamExtractor.downloadVideo(vid,folder)
        if result:            
            full_path_to_file = result.filepath
        elif result.status != 'canceled':            
            error_message = result.message
    finally:
        YDStreamExtractor.setOutputCallback(None)

capitalize = re.compile(r'(^|(?<=[\s' +
  re.escape(string.punctuation.replace("'", "")) + '])).')

def fix_title(title):
	upper = False
	lower = False
	cap = False
	tags = dict.fromkeys([ 'B', 'I', 'UPPERCASE', 'LOWERCASE',
	  'CAPITALIZE', 'LIGHT' ], False)
	colors = 0
	result, brack, rest = title.partition('[')
	while brack and rest:
		tag, end, rest = rest.partition(']')
		if tag and end:
			if tag[0] == '/':
				tag = tag[1:]
				on = False
			else:
				on = True
			if tag in tags:
				if on:
					if '[/'+tag+']' in rest:
						tags[tag] = True
					else:
						result += '['
						rest = tag+']'+rest
				elif tags[tag]: tags[tag] = False
				else:
					result += '[/'
					rest = tag+']'+rest
			elif on:
				if tag.startswith('COLOR') and \
				  '[/COLOR]' in rest: colors += 1
				elif tag == 'CR': result += '_'
				else:
					result += '['
					rest = tag+']'+rest
			elif tag == 'COLOR' and colors: colors -= 1
			else:
				result += '[/'
				rest = tag+']'+rest
		else:
			result += '['
			rest = tag+end+rest
		before, brack, rest = rest.partition('[')
		if tags['UPPERCASE']: before = before.upper()
		if tags['LOWERCASE']: before = before.lower()
		if tags['CAPITALIZE']:
			before = capitalize.sub(lambda x: x.group().upper(),
			  before)
		result += before
	return re.sub(r'[_\s/:]+', '_', (result + brack))

def ask_for_url(url):
	return xbmcgui.Dialog().input(translation(30026), defaultt = url)

def nonecmp(a, b):
	for ai, bi in zip(a, b):
		if ai is None or bi is None: continue
		return (ai > bi) - (ai < bi)

	return 0

class NoneCmp:
	def comparator(name):
		op = getattr(operator, name)
		eq_result = op(0, 0)

		def compare(lhs, rhs):
			for li, ri in zip(lhs.items, rhs.items):
				if li is not None and ri is not None and li != ri:
					return op(li, ri)
			return eq_result

		setattr(NoneCmp, name, compare)
	def __init__(self, *items, **kw):
		self.items = items
		for key, val in kw.items(): setattr(self, key, val)

def comparator(name):
	op = getattr(operator, name)
	eq_result = op(0, 0)

	def compare(lhs, rhs):
		for li, ri in zip(lhs.items, rhs.items):
			if li is not None and ri is not None and li != ri:
				return op(li, ri)
		return eq_result

	setattr(NoneCmp, '__'+name+'__', compare)

comparator('lt')
comparator('le')
comparator('eq')
comparator('ne')
comparator('ge')
comparator('gt')

def downloadffmpg(file,title,headers):    
	debug("Start downloadffmpg")
	import subprocess

	name = fix_title(title)[0:50]+".mp4"
	outpath = os.path.join(folder, name)

	overwrite = '-n'
	while os.path.exists(outpath):
		answer = xbmcgui.Dialog().select(translation(30018).format(name),
		  [ translation(30019), translation(30020), translation(30021) ],
		  preselect = 1)
		if answer == 0: quit()
		if answer == 1:
			overwrite = '-y'
			break
		if answer == 2:
			newname = xbmcgui.Dialog().input(translation(30022), defaultt=name)
			if not newname: continue
			if not newname.endswith('.mp4'): newname += '.mp4'
			name = newname
			outpath = os.path.join(folder, name)

	if headers: inputopt = ['-headers', headers]
	else: inputopt = []

	inputopt += ['-i']

	if hasattr(subprocess, 'DEVNULL'):
		DEVNULL = subprocess.DEVNULL
		closedevnull = lambda: None
	else:
		DEVNULL = open(os.devnull, 'r+')
		closedevnull = DEVNULL.close

	if ffprobefile:
		if askurl and not askstreams:
			file = ask_for_url(file)
			
		while True:
			if not file:
				closedevnull()
				return True

			ffprobe = subprocess.Popen([ ffprobefile,
			  '-of', 'json', '-show_format', '-show_streams' ]+inputopt+[file],
			  stdin=DEVNULL, stdout=subprocess.PIPE, stderr=DEVNULL,
			  universal_newlines=True, # Python 2/3 compat
			)

			info = json.loads(ffprobe.communicate()[0])
			ffprobe.wait()
			if ffprobe.returncode != 0:
				closedevnull()
				return False

			try:
				duration = 1000000 * float(info['format']['duration'])
			except (KeyError, ValueError):
				duration = None

			streams = {}
			dispo = [ 'dub', 'original', 'comment', 'lyrics', 'karaoke', 'forced', 'hearing_impaired', 'visual_impaired', 'clean_effects', 'attached_pic', 'timed_thumbnails' ]
			for index, stream in enumerate(info['streams']):
				stream_key = [stream['codec_type'],
				  stream.get('tags', {}).get('language', 'und')]
				try:
					disposition = stream['disposition']
				except KeyError:
					stream_key.extend([0] * len(dispo))
				else:
					stream_key.extend(disposition.get(d, 0) for d in dispo)

				# hashable
				stream_key = tuple(stream_key)

				try:
					bitrate = int(stream['bit_rate'])
				except (KeyError, ValueError):
					try:
						bitrate = int(stream['max_bit_rate'])
					except (KeyError, ValueError):
						bitrate = None

				if stream['codec_type'] == 'video':
					size = stream['coded_width'] * stream['coded_height']
					rate = 'avg_frame_rate'
				elif stream['codec_type'] == 'audio':
					size = stream['channels']
					rate = 'sample_rate'
				else:
					size = None
					rate = None

				if rate is not None:
					try:
						rate = Fraction(stream[rate])
					except (KeyError, ValueError):
						rate = None

				streams.setdefault(stream_key, []).append(
				  NoneCmp(bitrate, size, rate, index = index)
				)

			preselect = []
			all_streams = []
			for key in sorted(streams.keys()):
				stream_list = streams[key]
				stream_list.sort(reverse = True)
				if info['streams'][stream_list[0].index]['codec_type'] != \
				  'data':
					preselect.append(len(all_streams))
				all_streams.extend(stream.index for stream in stream_list)

			if not askstreams:
				streams = preselect
				break

			options = []
			for stream in all_streams:
				option = info['streams'][stream]
				streamtype = option['codec_type']
				string = streamtype.title() + \
				  ' ('+option.get('codec_name', 'unknown')

				language = option.get('tags', {}).get('language', 'und')
				if language != 'und':
					string += ', '+language

				if streamtype == 'video':
					string += ', '+str(option['coded_width'])+'x'+ \
					  str(option['coded_height'])
				elif streamtype == 'audio':
					string += ', '+str(option['channels'])+ \
					  ' channels '+option['channel_layout']

				try:
					bitrate = int(option['bit_rate'])
				except (KeyError, ValueError):
					try:
						bitrate = int(option['max_bit_rate'])
					except (KeyError, ValueError):
						bitrate = None

				if bitrate is not None:
					string += ', '+option['bit_rate']+' bps'

				string += ')'

				dispos = [ key for key, value
				  in option['disposition'].items() if value ]

				if dispos:
					string += ' ['+', '.join(dispos)+']'

				options.append(string)

			streams = xbmcgui.Dialog().multiselect(translation(30025),
			  options, preselect = preselect)
			if streams is not None: break
			if askurl:
				file = ask_for_url(file)
			else:
				closedevnull()
				return True

		streams = [info['streams'][all_streams[i]]['index'] for i in streams]
	else:
		if askurl:
			file = ask_for_url(file)
			if not file:
				closedevnull()
				return True

		duration = None

		streams = []

	if bg: dialog = xbmcgui.DialogProgressBG()
	else: dialog = xbmcgui.DialogProgress()
	dialog.create(translation(30002), title)

	if duration is None: progopt = []
	else: progopt = ['-progress', '-'] # Machine-readable progress

	commandline = [ ffmpgfile, overwrite ]
	commandline += progopt
	commandline += inputopt
	commandline.append(file)
	for stream in streams:
		commandline += [ '-map', ':'+str(stream) ]
	commandline += [ '-codec', 'copy', '--', fsenc(outpath) ]

	notice(str(commandline))

	ffmpeg = subprocess.Popen(commandline,
	  stdin=DEVNULL, stdout=subprocess.PIPE, stderr=DEVNULL,
	  universal_newlines=True, # Python 2/3 compat
	)

	cancelled = False

	if duration is not None:
		while True:
			key, _, value = ffmpeg.stdout.readline().partition('=')
			if not _:
				if key: continue
				else: break

			if key == 'out_time_ms':
				dialog.update(int(100 * float(value) / duration))
			elif not bg and key == 'progress':
				if dialog.iscanceled():
					ffmpeg.terminate()
					cancelled = True
					break
		ffmpeg.wait()
	elif bg:
		ffmpeg.wait()
	else:
		while ffmpeg.poll() is None:
			time.sleep(1)
			if dialog.iscanceled():
				ffmpeg.terminate()
				ffmpeg.wait()
				cancelled = True
				break

	closedevnull()

	dialog.close()

	if cancelled:
		try: os.remove(outpath)
		except OSError:
			xbmcgui.Dialog().ok(translation(30016), translation(30017))
		return True

	if ffmpeg.returncode != 0: return False

	dialog = xbmcgui.Dialog()
	if bg: done = dialog.notification
	else: done = dialog.ok
	done(translation(30004), title)
	return True

#MAIN    
# warning about abuse
if warning=="false":
    dialog = xbmcgui.Dialog()
    erg=dialog.yesno(translation(30007), translation(30008)+'\n'+translation(30009)+'\n'+translation(30010))
    if erg==1:
       addon.setSetting("warning","true")
    else:
      quit()    

path = sys.listitem.getPath()
title = sys.listitem.getLabel()

notice(repr(title))

# start video
kodi_player = xbmc.Player()
kodi_player.play(path, sys.listitem)
time.sleep(10) 
videoda=0

# until the first file is played read file
while videoda==0 :
    try:
        file=kodi_player.getPlayingFile()
        debug("-----> "+file)
        if not file=="":
            videoda=1
    except:
        pass 

file, _, headers = file.partition('|')

if headers:
	new_headers = ''
	for header in headers.split('&'):
		name, _, content = header.partition('=')
		new_headers += name + ':' + content + '\n'
	headers = new_headers

# use FFmpeg or youtube-dl
if not ffmpgfile=="":
	kodi_player.stop()
	if not downloadffmpg(file,title,headers):
		if xbmcgui.Dialog().yesno(translation(30005), translation(30006)):
			kodi_player.play(path, sys.listitem)
			time.sleep(5)
			ffdir,fffile=os.path.split(ffmpgfile)
			debug("FFDIR :"+ffdir)
			downloadyoutube(file,ffdir=ffdir)  

else:
	downloadyoutube(file)
