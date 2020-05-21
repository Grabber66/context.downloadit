#!/usr/bin/python3

OUT_DIR = 'public'
ADDON = 'context.downloadit'
REPO_STABLE = 'repository.'+ADDON
REPO_UNSTABLE = REPO_STABLE+'.unstable'

import re
import subprocess
import os
import shutil
from zipfile import ZipFile, ZipInfo
from xml.etree import ElementTree
from hashlib import md5 as checksum
from string import Template

is_stable_version = re.compile(r'[0-9]+(\.[0-9]+)*$').match

class Version:
	regex = re.compile(r'(?P<number>[0-9]+)|(?P<tilde>~)|(?P<string>[^0-9~]+)')

	def __init__(self, version):
		self.version = version = version.casefold()
		self.components = []
		while version:
			next_comp = self.regex.match(version)
			if next_comp is None:
				raise Exception
			version = version[next_comp.end():]

			number = next_comp.group('number')
			if number is not None:
				self.components.append((0, int(number)))
				continue
			if next_comp.group('tilde') is not None:
				self.components.append((-1, None))
				continue
			string = next_comp.group('string')
			if string is not None:
				self.components.append((1, string))
				continue

			raise Exception

	def is_stable(self):
		return len(self.components) % 2 == 1 and \
		  all(s == '.' for _, s in self.components[1::2]) and \
		  all(t == 0 for t, _ in self.components[0::2])

	def __str__(self):
		return self.version

	def __eq__(lhs, rhs):
		return lhs.components == rhs.components

	def cmp(lhs, rhs):
		if lhs == rhs: return 0

		lhslen = len(lhs.components)
		rhslen = len(rhs.components)
		if (lhslen < rhslen and lhs.components == rhs.components[:lhslen] and
		  rhs.components[lhslen][0] < 0): return -1
		if (lhslen > rhslen and lhs.components[:rhslen] == rhs.components and
		  lhs.components[rhslen][0] < 0): return -1
		if lhs.components < rhs.components: return -1
		else:                               return  1

	def __lt__(lhs, rhs):
		return lhs.cmp(rhs) < 0
	def __le__(lhs, rhs):
		return lhs.cmp(rhs) <= 0
	def __gt__(lhs, rhs):
		return lhs.cmp(rhs) > 0
	def __ge__(lhs, rhs):
		return lhs.cmp(rhs) >= 0

class AddonList:
	def __init__(self, path):
		self.f = open(path, 'wb')
		self.f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n<addons>\n')
	def add(self, addon_xml):
		addon_xml.write(self.f, encoding="utf8", xml_declaration=False)
		self.f.write(b'\n')
	def close(self):
		self.f.write(b'</addons>\n')
		self.f.close()

	def __enter__(self):
		return self
	def __exit__(self, exc_type, exc_value, exc_traceback):
		self.close()
		return False # reraise exception

def read_addon_xml(path):
	return ElementTree.parse(os.path.join(path, 'addon.xml'))

def open_zipfile(addon_xml, path):
	addon = addon_xml.getroot()
	addon_id = addon.get('id')
	version = addon.get('version')

	return ZipFile(os.path.join(path, addon_id, addon_id+'-'+version+'.zip'),
	  'w')

def make_addon(addon_xml = None, nightly = False, copytree = False,
		symlink = [], addons_xml = None, matrix_addons_xml = None):
	target = os.path.join(OUT_DIR, ADDON)

	if addon_xml is None: addon_xml = read_addon_xml(ADDON)

	addon_tag = addon_xml.getroot()

	symlink = list(symlink)

	if nightly:
		addon_tag.set('version', addon_tag.get('version')+'@nightly')
		symlink.append('-nightly')

	if copytree:
		symlink.append('')

	addon_xml_info = ZipInfo.from_file(os.path.join(ADDON, 'addon.xml'))

	# Poor man's context manager without auto-close
	addon_zip = open_zipfile(addon_xml, OUT_DIR)
	try:
		with addon_zip.open(ZipInfo.from_file(
		  os.path.join(ADDON, 'addon.xml')), 'w') as zip_addon_xml:
			addon_xml.write(zip_addon_xml, encoding='UTF-8',
			  xml_declaration=True)
		if addons_xml is not None: addons_xml.add(addon_xml)

		addon_tag.set('version', addon_tag.get('version') + '+matrix')
		requires = addon_tag.find('requires')
		for imp in addon_tag.find('requires').iterfind('import'):
			if imp.get('addon') == 'xbmc.python':
				imp.set('version', '3.0.0')

	except:
		addon_zip.close()
		raise

	with addon_zip, open_zipfile(addon_xml, OUT_DIR) as matrix_zip:
		if matrix_addons_xml is not None:
			matrix_addons_xml.add(addon_xml)

		walker = walk(ADDON)
		path, dirnames, filenames = next(walker)

		while True:
			for filename in filenames:
				if filename.startswith('.'):
					continue

				src = os.path.join(ADDON, path, filename)
				if copytree:
					shutil.copy2(src, os.path.join(OUT_DIR, src))
				if path != '' or filename != 'addon.xml':
					addon_zip.write(src)
					matrix_zip.write(src)

			try:
				path, dirnames, filenames = walker.send(dirname for dirname
				  in dirnames if dirname.startswith('.'))
			except StopIteration:
				break

			if copytree: os.mkdir(os.path.join(OUT_DIR, ADDON, path))

		with matrix_zip.open(ZipInfo.from_file(
		  os.path.join(ADDON, 'addon.xml')), 'w') as matrix_addon_xml:
			addon_xml.write(matrix_addon_xml, encoding='UTF-8',
			  xml_declaration=True)

	basepath = os.path.join(OUT_DIR, ADDON)
	for link_suffix in symlink:
		for zipfile, suffix in [ (addon_zip, ''), (matrix_zip, '+matrix') ]:
			os.symlink(os.path.relpath(zipfile.filename, basepath),
			           os.path.join(basepath, ADDON+link_suffix+suffix+'.zip'))

def make_repo(repo):
	target = os.path.join(OUT_DIR, repo)

	os.mkdir(os.path.join(OUT_DIR, repo))
	addon_xml = read_addon_xml(repo)

	walker = walk(repo)

	with open_zipfile(addon_xml, OUT_DIR) as repo_zip:
		path, dirnames, filenames = next(walker)

		while True:
			for filename in filenames:
				if filename.startswith('.'): continue
				src = os.path.join(repo, path, filename)
				shutil.copy2(src, os.path.join(OUT_DIR, src))
				repo_zip.write(src)

			try:
				path, dirnames, filenames = walker.send(dirname for dirname
				   in dirnames if dirname.startswith('.'))
			except StopIteration:
				break

			os.mkdir(os.path.join(OUT_DIR, repo, path))

	os.symlink(os.path.relpath(repo_zip.filename, os.path.join(OUT_DIR, repo)),
	           os.path.join(OUT_DIR, repo, repo+'.zip'))

	return addon_xml

def walk(root, path=''):
	fullpath = os.path.join(root, path)

	listing = os.listdir(fullpath)
	files = []
	dirs = []
	for name in listing:
		newpath = os.path.join(fullpath, name)
		if os.path.isdir(newpath): dirs.append(name)
		elif os.path.isfile(newpath): files.append(name)

	exclude = set((yield path, dirs.copy(), files.copy()))

	for dirname in dirs:
		if dirname in exclude: continue
		yield from walk(root, os.path.join(path, dirname))

os.mkdir(OUT_DIR)

with open('index.html') as index:
	index_template = Template(index.read())

with open('releases.html.entry') as r_entry:
	release_template = Template(r_entry.read())

with open('releases.html.foot') as r_foot:
	release_foot = r_foot.read()

head = subprocess.run([ 'git', 'rev-parse', '--symbolic-full-name', 'HEAD' ],
  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
  universal_newlines=True).stdout.strip()

if head.startswith('refs/heads/'):
	head = head[len('refs/heads/'):]
else:
	head = None

with AddonList(os.path.join(OUT_DIR, 'addons.xml')) as stable, \
     AddonList(os.path.join(OUT_DIR, 'addons.unstable.xml')) as unstable, \
     AddonList(os.path.join(OUT_DIR, 'addons.matrix.xml')) as stable_matrix, \
     AddonList(os.path.join(OUT_DIR, 'addons.unstable.matrix.xml')) as \
	   unstable_matrix, \
     open(os.path.join(OUT_DIR, 'releases.html'), 'w') as releases:

	stable_repo = make_repo(REPO_STABLE)
	stable.add(stable_repo)
	stable_repo_version = stable_repo.getroot().get('version')
	del stable_repo

	unstable_repo = make_repo(REPO_UNSTABLE)
	stable.add(unstable_repo)
	unstable_repo_version = unstable_repo.getroot().get('version')
	del unstable_repo

	with open('releases.html.head') as r_head:
		shutil.copyfileobj(r_head, releases)

	os.mkdir(os.path.join(OUT_DIR, ADDON))

	make_addon(nightly = True)

	current = unstable
	current_matrix = unstable_matrix

	stable_version = None
	unstable_version = None

	had_stable = False
	symlink = [ '-unstable' ]

	revs = subprocess.run([ 'git', 'rev-list', 'HEAD' ],
	  universal_newlines=True,
	  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
	).stdout.splitlines()

	if head is None: head = revs[0]

	cmd = [ 'git', 'for-each-ref', '--python',
	  '--format', '%(objectname): (%(refname), %(creatordate:short)),',
	  'refs/tags/v*' ]
	for rev in revs:
		cmd += [ '--points-at', rev ]

	versions = eval('{' + subprocess.run(cmd, universal_newlines = True,
	  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE).stdout + '}')

	for rev in revs:
		try: tag, date = versions[rev]
		except KeyError: continue

		subprocess.run([ 'git', 'checkout', rev ], stdin=subprocess.DEVNULL)

		addon_xml = read_addon_xml(ADDON)

		version = addon_xml.getroot().get('version')

		if not had_stable and is_stable_version(version):
			copytree = True

			stable_version = version

			current = stable
			current_matrix = stable_matrix

			had_stable = True
		else:
			copytree = False

		if unstable_version is None:
			unstable_version = version

		news = ''
		for extension in addon_xml.getroot().iterfind('extension'):
			if extension.get('point') == 'xbmc.addon.metadata':
				news_elem = extension.find('news')
				if news_elem is not None:
					news = news_elem.text
					break

		releases.write(release_template.substitute(
			VERSION = version,
			DATE = date,
			NEWS = news,
		))

		make_addon(addon_xml = addon_xml, copytree = copytree,
		  symlink = symlink, addons_xml = current,
		  matrix_addons_xml = current_matrix)
		symlink = []

	releases.write(release_foot)

subprocess.run([ 'git', 'checkout', head ])

for stable in ['', '.unstable']:
	for matrix in ['', '.matrix']:
		name = 'addons'+stable+matrix+'.xml'
		path = os.path.join(OUT_DIR, name)
		check = checksum()
		with open(path, 'rb') as f:
			chunk = f.read(4096)
			while chunk:
				check.update(chunk)
				chunk = f.read(4096)
		with open(path+'.md5', 'w', newline='\n') as md5file:
			md5file.write(check.hexdigest()+'  '+name+'\n')

with open(os.path.join(OUT_DIR, 'index.html'), 'w') as index:
	index.write(index_template.substitute(
		STABLE_VERSION = stable_version,
		UNSTABLE_VERSION = unstable_version,
		STABLE_REPO_VERSION = stable_repo_version,
		UNSTABLE_REPO_VERSION = unstable_repo_version,
	))
