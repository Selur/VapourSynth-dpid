project('VapourSynth-dpid', 'cpp',
  default_options : ['buildtype=release', 'b_ndebug=if-release', 'cpp_std=c++17', 'warning_level=3'],
  meson_version : '>=0.51.0',
  version : '8.1.0'
)

# Prefer system VapourSynth headers, fall back to the vendored API 4 headers.
system_vs_dep = dependency('vapoursynth', version : '>=55', required : false)
if system_vs_dep.found()
  vapoursynth_dep = system_vs_dep.partial_dependency(compile_args : true, includes : true)
else
  vapoursynth_dep = declare_dependency(include_directories : include_directories('include/vapoursynth'))
endif

cxx = meson.get_compiler('cpp')
if cxx.get_argument_syntax() == 'gcc' or cxx.get_id() == 'clang-cl'
  add_project_arguments('-Wno-unused-parameter', language : 'cpp')
endif

# VapourSynth only autoloads *.dylib on macOS, while Meson defaults to *.so for modules.
suffix = host_machine.system() == 'darwin' ? 'dylib' : []

if get_option('python_package')
  # Same layout as the VapourSynth PyPI package autoloads from: site-packages/vapoursynth/plugins
  py = import('python').find_installation(pure : false)
  install_dir = join_paths(py.get_install_dir(), 'vapoursynth', 'plugins')
else
  libdir = join_paths(get_option('prefix'), get_option('libdir'))
  if system_vs_dep.found()
    libdir = system_vs_dep.get_variable(pkgconfig : 'libdir', default_value : libdir)
  endif
  install_dir = join_paths(libdir, 'vapoursynth')
endif

shared_module('dpid', 'Source/Source.cpp',
  dependencies : vapoursynth_dep,
  install : true,
  install_dir : install_dir,
  name_suffix : suffix,
  gnu_symbol_visibility : 'hidden'
)
