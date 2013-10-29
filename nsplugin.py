import os, ctypes as c, re, logging
log = logging.getLogger(__name__)

UAGENT = c.c_char_p('nsplugin.py')

SEARCH_PATH = os.getenv('MOZ_PLUGIN_PATH', '').split(':') + [
	os.path.expanduser('~/.mozilla/plugins/'),
	'/usr/lib/mozilla/plugins/',
	'/usr/lib/browser/plugins/'
]

# translated from npapi.h:

_NPError = c.c_int16
_NPBool = c.c_ubyte
_NPReason = c.c_int16
_NPNVariable = c.c_int

_NP_EMBED = 1
_NP_FULL = 2
_NP_NORMAL = 1
_NP_ASFILE = 3
_NP_ASFILEONLY = 4
_NPRES_DONE = 0
_NPRES_NETWORK_ERR = 1
_NPNVGtk2 = 2
_NPNVToolkit = 13 | 1<<28
_NPNVSupportsXEmbedBool = 14
_NPNVprivateModeBool = 18
_NPWindowTypeWindow = 1

class NPError(Exception):
	values = '''
		NO_ERROR
		GENERIC_ERROR
		INVALID_INSTANCE_ERROR
		INVALID_FUNCTABLE_ERROR
		MODULE_LOAD_FAILED_ERROR
		OUT_OF_MEMORY_ERROR
		INVALID_PLUGIN_ERROR
		INVALID_PLUGIN_DIR_ERROR
		INCOMPATIBLE_VERSION_ERROR
		INVALID_PARAM
		INVALID_URL
		FILE_NOT_FOUND
		NO_DATA
		STREAM_NOT_SEEKABLE
	'''.split()
	def __init__(self, call, code):
		Exception.__init__(self, call + ' returned ' + self.values[code])
		self.code = code
for i, v in enumerate(NPError.values):
	setattr(NPError, v, i)

class _NPP_t(c.Structure):
	_fields_ = ('pdata', c.c_void_p), ('ndata', c.py_object)
_NPP = c.POINTER(_NPP_t)

class _NPStream(_NPP_t):
	_fields_ = (
		('url', c.c_char_p),
		('end', c.c_uint32),
		('lastmodified', c.c_uint32),
		('notifyData', c.c_void_p),
		('headers', c.c_char_p)
	)

class _NPSetWindowCallbackStruct(c.Structure):
	_fields_ = (
		('type', c.c_int32),
		('display', c.c_void_p),
		('visual', c.c_void_p),
		('colormap', c.c_uint32),
		('depth', c.c_uint)
	)
class _NPWindow(c.Structure):
	_fields_ = (
		('window', c.c_void_p),
		('x', c.c_int32),
		('y', c.c_int32),
		('width', c.c_uint32),
		('height', c.c_uint32),
		('clipRect', c.c_uint16 * 4),
		('ws_info', c.POINTER(_NPSetWindowCallbackStruct)),
		('type', c.c_int)
	)

# translated from npfunctions.h:

class _NPFuncs(c.Structure):
	_fields_ = ('size', c.c_uint16), ('version', c.c_uint16)
	def __init__(self):
		self.size = c.sizeof(self)

class _NPPluginFuncs(_NPFuncs):
	_fields_ = (
		('newp', c.CFUNCTYPE(_NPError, c.c_char_p, _NPP, c.c_uint16, c.c_int16, c.POINTER(c.c_char_p), c.POINTER(c.c_char_p), c.c_void_p)),
		('destroy', c.CFUNCTYPE(_NPError, _NPP, c.c_void_p)),
		('setwindow', c.CFUNCTYPE(_NPError, _NPP, c.c_void_p)),
		('newstream', c.CFUNCTYPE(_NPError, _NPP, c.c_char_p, c.c_void_p, _NPBool, c.POINTER(c.c_uint16))),
		('destroystream', c.CFUNCTYPE(_NPError, _NPP, c.c_void_p, _NPReason)),
		('asfile', c.CFUNCTYPE(None, _NPP, c.c_void_p, c.c_char_p)),
		('writeready', c.CFUNCTYPE(c.c_int32, _NPP, c.c_void_p)),
		('write', c.CFUNCTYPE(c.c_int32, _NPP, c.c_void_p, c.c_int32, c.c_int32, c.c_void_p)),
		('print_', c.c_void_p),
		('event', c.c_void_p),
		('urlnotify', c.CFUNCTYPE(None, _NPP, c.c_char_p, _NPReason, c.c_void_p)),
		('javaClass', c.c_void_p),
		('getvalue', c.c_void_p),
		('setvalue', c.c_void_p)
	)

class _NPNetscapeFuncs(_NPFuncs):
	_fields_ = (
		('geturl', c.c_void_p),
		('posturl', c.c_void_p),
		('requestread', c.c_void_p),
		('newstream', c.c_void_p),
		('write', c.c_void_p),
		('destroystream', c.c_void_p),
		('status', c.CFUNCTYPE(None, _NPP, c.c_char_p)),
		('uagent', c.CFUNCTYPE(c.c_char_p, _NPP)),
		('memalloc',  c.c_void_p),
		('memfree',  c.c_void_p),
		('memflush',  c.c_void_p),
		('reloadplugins', c.c_void_p),
		('getJavaEnv', c.c_void_p),
		('getJavaPeer', c.c_void_p),
		('geturlnotify', c.CFUNCTYPE(_NPError, _NPP, c.c_char_p, c.c_char_p, c.c_void_p)),
		('posturlnotify', c.c_void_p),
		('getvalue', c.CFUNCTYPE(_NPError, _NPP, _NPNVariable, c.c_void_p)),
		('setvalue', c.c_void_p),
		('invalidaterect', c.c_void_p),
		('invalidateregion', c.c_void_p),
		('forceredraw', c.c_void_p)
	)

# plugin host implementation:

	def __init__(self):
		_NPFuncs.__init__(self)
		self.version = 13

		def NPN_Status(inst, msg):
			log.info('NPN_Status: %r', msg)
		self.status = type(self.status)(NPN_Status)

		def NPN_UserAgent(inst):
			return c.cast(UAGENT, c.c_void_p).value
		self.uagent = type(self.uagent)(NPN_UserAgent)

		def NPN_GetURLNotify(inst, url, target, notifyData):
			log.debug('NPN_GetURLNotify: %r, %r', url, target)
			err = NPError.NO_ERROR
			if not target: err = inst.contents.ndata._do_stream(url, None, notifyData)
			inst.contents.ndata.plugin.plugin_funcs.urlnotify(inst, url, _NPRES_DONE, notifyData)
			return err
		self.geturlnotify = type(self.geturlnotify)(NPN_GetURLNotify)

		def NPN_GetValue(inst, var, valuep):
			if var == _NPNVToolkit: c.cast(valuep, c.POINTER(c.c_int)).contents.value = _NPNVGtk2
			elif var == _NPNVSupportsXEmbedBool: c.cast(valuep, c.POINTER(_NPBool)).contents.value = True
			elif var == _NPNVprivateModeBool: c.cast(valuep, c.POINTER(_NPBool)).contents.value = True
			else:
				log.warning('NPN_GetValue %i unhandled', var)
				return NPError.INVALID_PARAM
			return NPError.NO_ERROR
		self.getvalue = type(self.getvalue)(NPN_GetValue)

_netscape_funcs = _NPNetscapeFuncs()

def _check(call, code):
	if code != NPError.NO_ERROR: raise NPError(call, code)

class MimeType(object):
	def __init__(self, mimedesc):
		self.name, ext, self.desc = mimedesc.split(':', 2)
		self.ext = ext.split(',') if ext else []
	def __repr__(self):
		return '<MimeType: %s>' % self.name

class NSPlugin(object):
	def __init__(self, filename):
		self.filename = filename
		self.lib = c.CDLL(filename)
		self.lib.NP_GetMIMEDescription.restype = c.c_char_p
		self.lib.NP_GetValue.restype = _NPError
		self.lib.NP_Initialize.restype = _NPError
		self.lib.NP_Shutdown.restype = _NPError
		# regex instead of simple split because some plugins (openjdk) have semicolons in the mimetypes
		self.mimetypes = [MimeType(s) for s in re.findall('([^:]*:[^:]*:[^;]*);?', self.lib.NP_GetMIMEDescription())]
		out = c.c_char_p()
		self.lib.NP_GetValue(None, 1, c.byref(out))
		self.name = out.value
		self.lib.NP_GetValue(None, 2, c.byref(out))
		self.desc = out.value
		self.plugin_funcs = None
	def __repr__(self):
		return '<NSPlugin: %s>' % self.filename
	def new(self, *args):
		if not self.plugin_funcs:
			self.plugin_funcs = _NPPluginFuncs()
			_check('NP_Initialize', self.lib.NP_Initialize(c.byref(_netscape_funcs), c.byref(self.plugin_funcs)))
		return NSPluginInstance(self, *args)
	def shutdown(self):
		if self.plugin_funcs:
			self.lib.NP_Shutdown()
			self.plugin_funcs = None

class NSPluginInstance(object):
	def __init__(self, plugin, filename, mimetype, xid, width, height, args=()):
		self.plugin = plugin
		self.filename = filename
		self.instance = _NPP_t()
		self.instance.ndata = self
		argn = (c.c_char_p*len(args))()
		argv = (c.c_char_p*len(args))()
		for i, (n, v) in enumerate(args):
			argn[i] = n
			argv[i] = v
		_check('newp', plugin.plugin_funcs.newp(mimetype, c.byref(self.instance),
			_NP_EMBED if args else _NP_FULL, len(args), argn, argv, None))
		self.np_window = _NPWindow()
		self.np_window.type = _NPWindowTypeWindow
		self.np_window.window = xid
		self.ws_info = _NPSetWindowCallbackStruct()
		self.np_window.ws_info = c.pointer(self.ws_info)
		self.set_size(width, height)
		_check('do_stream', self._do_stream(os.path.abspath(filename), mimetype, None))
	def __repr__(self):
		return '<NSPluginInstance: %s, %s>' % (self.plugin.filename, self.filename)
	def _do_stream(self, src, mimetype, notify_data):
		if src.startswith('file://'): src = src[7:]
		if ':' in src:
			log.error('Invalid url: %r', src)
			return NPError.INVALID_URL
		if not src.startswith('/'):
			src = os.path.join(os.path.dirname(os.path.abspath(self.filename)), src)
		reason = _NPRES_DONE
		np_stream = _NPStream()
		np_stream.url = 'file://' + src
		try: np_stream.end = os.path.getsize(src)
		except Exception: log.exception('could not get filesize of %r', src)
		np_stream.notifyData = notify_data
		stype = c.c_uint16(_NP_NORMAL)
		_check('newstream', self.plugin.plugin_funcs.newstream(c.byref(self.instance), mimetype, c.byref(np_stream), False, c.byref(stype)))
		if stype.value == _NP_ASFILE or stype.value == _NP_ASFILEONLY:
			self.plugin.plugin_funcs.asfile(c.byref(self.instance), c.byref(np_stream), src)
		else:
			try:
				with open(src, 'rb') as f:
					offset = 0
					while True:
						write_ready = min(1<<20, self.plugin.plugin_funcs.writeready(c.byref(self.instance), c.byref(np_stream)))
						buf = f.read(write_ready)
						if not buf: break
						while buf:
							written = self.plugin.plugin_funcs.write(c.byref(self.instance), c.byref(np_stream), offset, len(buf), buf)
							offset += written
							buf = buf[written:]
					log.debug('wrote %d bytes', written)
			except Exception:
				log.exception('error streaming %r', src)
				reason = _NPRES_NETWORK_ERR
		_check('destroystream', self.plugin.plugin_funcs.destroystream(c.byref(self.instance), c.byref(np_stream), reason))
		return NPError.NO_ERROR
	def set_size(self, width, height):
		self.np_window.width = width
		self.np_window.height = height
		_check('setwindow', self.plugin.plugin_funcs.setwindow(c.byref(self.instance), c.byref(self.np_window)))
	def close(self):
		saved_data = c.c_void_p();
		_check('destroy', self.plugin.plugin_funcs.destroy(c.byref(self.instance), c.byref(saved_data)))
		if saved_data: log.warning('leaking saved data')
		del self.instance # break reference cycle

def find_plugins(paths=None):
	if paths is None: paths = SEARCH_PATH
	for p in paths:
		if os.path.isdir(p):
			for f in os.listdir(p):
				try:
					yield NSPlugin(os.path.join(p, f))
				except Exception:
					log.exception('Could not load plugin %s', os.path.join(p, f))

