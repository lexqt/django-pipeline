from __future__ import unicode_literals

from django.contrib.staticfiles.storage import staticfiles_storage
from django.contrib.staticfiles.finders import find
from django.core.files.base import ContentFile
from django.utils.encoding import smart_str

try:
    from django.utils.module_loading import import_string
except ImportError:
    from django.utils.module_loading import import_by_path as import_string


from pipeline.compilers import Compiler
from pipeline.compressors import Compressor
from pipeline.conf import settings
from pipeline.exceptions import PackageNotFound
from pipeline.glob import glob
from pipeline.signals import css_compressed, js_compressed


class Package(object):
    def __init__(self, config):
        self.config = config
        self._paths = []
        self._dyn_sources = []
        self._templates = []
        self._parsed = False

    def _parse(self):
        if self._parsed:
            return
        dyn_src_prefix = settings.PIPELINE_DYN_SOURCE_PREFIX
        dyn_prefix_len = len(dyn_src_prefix)
        tmpl_ext = settings.PIPELINE_TEMPLATE_EXT
        for pattern in self.config.get('source_filenames', []):
            if pattern.startswith(dyn_src_prefix):
                func = import_string(pattern[dyn_prefix_len:])
                self._dyn_sources.append(func)
                continue
            for path in glob(pattern):
                if path.endswith(tmpl_ext):
                    target = self._templates
                else:
                    target = self._paths
                if path not in target and find(path):
                    target.append(str(path))
        self._parsed = True

    @property
    def dyn_sources(self):
        self._parse()
        return self._dyn_sources

    @property
    def paths(self):
        self._parse()
        return self._paths

    @property
    def templates(self):
        self._parse()
        return self._templates

    @property
    def output_filename(self):
        return self.config.get('output_filename')

    @property
    def extra_context(self):
        return self.config.get('extra_context', {})

    @property
    def template_name(self):
        return self.config.get('template_name')

    @property
    def variant(self):
        return self.config.get('variant')

    @property
    def manifest(self):
        return self.config.get('manifest', True)


class Packager(object):
    def __init__(self, storage=None, verbose=False, css_packages=None, js_packages=None):
        if storage is None:
            storage = staticfiles_storage
        self.storage = storage
        self.verbose = verbose
        self.compressor = Compressor(storage=storage, verbose=verbose)
        self.compiler = Compiler(storage=storage, verbose=verbose)
        if css_packages is None:
            css_packages = settings.PIPELINE_CSS
        if js_packages is None:
            js_packages = settings.PIPELINE_JS
        self.packages = {
            'css': self.create_packages(css_packages),
            'js': self.create_packages(js_packages),
        }

    def package_for(self, kind, package_name):
        try:
            return self.packages[kind][package_name]
        except KeyError:
            raise PackageNotFound(
                "No corresponding package for %s package name : %s" % (
                    kind, package_name
                )
            )

    def individual_url(self, filename):
        return self.storage.url(filename)

    def pack_stylesheets(self, package, **kwargs):
        return self.pack(package, self.compressor.compress_css, css_compressed,
                         output_filename=package.output_filename,
                         variant=package.variant, **kwargs)

    def compile(self, paths, force=False):
        return self.compiler.compile(paths, force=force)

    def pack(self, package, compress, signal, **kwargs):
        output_filename = package.output_filename
        if self.verbose:
            print("Saving: %s" % output_filename)
        paths = self.compile(package.paths, force=True)
        content = compress(paths, **kwargs)
        self.save_file(output_filename, content)
        signal.send(sender=self, package=package, **kwargs)
        return output_filename

    def pack_javascripts(self, package, **kwargs):
        return self.pack(
            package, self.compressor.compress_js, js_compressed,
            templates=package.templates, dyn_sources=package.dyn_sources,
            **kwargs
        )

    def pack_templates(self, package):
        return self.compressor.compile_templates(package.templates)

    def pack_dyn_sources(self, package):
        return self.compressor.compile_dyn_sources(package.dyn_sources)

    def save_file(self, path, content):
        return self.storage.save(path, ContentFile(smart_str(content)))

    def create_packages(self, config):
        packages = {}
        if not config:
            return packages
        for name in config:
            packages[name] = Package(config[name])
        return packages
