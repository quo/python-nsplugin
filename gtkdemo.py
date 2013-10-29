#!/usr/bin/python2

import logging, argparse, glib, gtk, nsplugin
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)
glib.threads_init()

class NSPluginViewer(gtk.Socket):
	def __init__(self):
		gtk.Socket.__init__(self)
		self.set_size_request(0, 0)
		self.modify_bg(gtk.STATE_NORMAL, gtk.gdk.Color(0, 0, 0))
		self.instance = self.plugin = self.filename = self.mimetype = None
		self.connect('plug-removed', lambda w: True)
		self.connect('realize', self._create_instance)
		self.connect('unrealize', self._destroy_instance)
		self.connect('size-allocate', lambda w, a: self.instance and self.instance.set_size(a.width, a.height))
	def _create_instance(self, *a):
		if not self.instance and self.filename and self.get_id():
			self.instance = self.plugin.new(self.filename, self.mimetype, self.get_id(), self.allocation.width, self.allocation.height, self.args)
	def _destroy_instance(self, *a):
		if self.instance:
			self.instance.close()
			self.instance = None
	def set_file(self, plugin, filename, mimetype, args):
		self._destroy_instance()
		self.plugin = plugin
		self.filename = filename
		self.mimetype = mimetype
		self.args = args
		self._create_instance()

def get_plugin(plugins, ext, mimetype):
	for p in plugins:
		for m in p.mimetypes:
			if ext in m.ext or mimetype == m.name:
				return p, m.name
	return None, None

def main():

	parser = argparse.ArgumentParser(description='View a file using a browser plugin.')
	parser.add_argument('file', metavar='FILE', help='the file to open')
	parser.add_argument('args', metavar='ARG=VALUE', nargs='*', help='plugin arguments')
	parser.add_argument('-t', '--mimetype', help='mimetype of the file')
	parser.add_argument('-p', '--plugin', help='plugin library to use')
	args = parser.parse_args()

	pluginargs = [a.split('=', 1) for a in args.args]

	ext = None if args.mimetype else args.file.rsplit('.', 1)[-1]
	if args.plugin:
		plugin = nsplugin.NSPlugin(args.plugin)
		plugins = [plugin]
		mimetype = args.mimetype
		if not mimetype: _, mimetype = get_plugin(plugins, ext, None)
		if not mimetype: mimetype = plugin.mimetypes[0].name
	else:
		plugins = list(nsplugin.find_plugins())
		plugin, mimetype = get_plugin(plugins, ext, args.mimetype)
	if not plugin: exit('No plugin found for %r' % args.file)

	print 'Loaded plugins:'
	print
	for p in plugins:
		print 'Name:', p.name
		print 'File:', p.filename
		print 'Description:', p.desc
		print 'Mimetypes:'
		for m in p.mimetypes:
			print ' ', m.name.ljust(32), ','.join(m.ext).ljust(16), m.desc
		print

	print 'Using plugin %r and mimetype %r for %r' % (plugin.filename, mimetype, args.file)
	print 'Plugin arguments: %r' % pluginargs

	w = gtk.Window()
	w.set_default_size(640, 480)
	w.connect('destroy', gtk.main_quit)
	v = NSPluginViewer()
	w.add(v)
	w.show_all()
	v.set_file(plugin, args.file, mimetype, pluginargs)
	gtk.main()

	for p in plugins: p.shutdown()

if __name__ == '__main__': main()
