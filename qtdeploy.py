#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
  Copyright (c) 2023, D3vC4t <d3vc4t777@gmail.com>
  All rights reservedself.
  
  SPDX-License-Identifier: BSD-3-Clause
  For full license text, see the LICENSE_Lavis file in the repo root or https://opensource.org/licenses/BSD-3-Clause

  I started to play with Qt recently and tested several linux deploy helpers.
  Anyhow, all of them have some issues on my machine:
  
    1. https://github.com/probonopd/linuxdeployqt: the latest version doesn't work on my Ubuntu 22.04.2 LTS;
    2. https://github.com/QuasarApp/CQtDeployer: this one seems work, but unfornately, the zip version will miss title bar;

  This is only a demo tool and work as my expection and you should take your own risk to use this script.
"""
import os
import sys
import shutil
import argparse
import subprocess

SCRIPT_VERSION = "0.1.0"

START_SCRIPT = """#!/bin/sh
appname=`basename $0 | sed s,\\.sh$,,`

dirname=`dirname $0`
tmp="${dirname#?}"

if [ "${dirname%%$tmp}" != "/" ]; then
  dirname=$PWD/$dirname
fi
export LD_LIBRARY_PATH="$dirname/%s"
$dirname/%s/$appname "$@"
"""

def die(s):
    sys.stderr.write("[!] %s\n" % s)
    sys.exit(1)

class CommandLineParser:
    DEFAULT_OUTPUT_DIR = "out"
    def __init__(self):
        pr = argparse.ArgumentParser(description="Linux Qt Application Deployment")
        pr.add_argument("-q", "--qmake", help="qmake file")
        pr.add_argument("-f", "--file", help="qt application file")
        pr.add_argument("-o", "--out", default=self.DEFAULT_OUTPUT_DIR, help="output dir(default: %s)" % self.DEFAULT_OUTPUT_DIR)
        pr.add_argument("-L", "--no-libraries", action="store_true", help="don't collect libraries")
        pr.add_argument("-P", "--no-plugins", action="store_true", help="don't collect plugins")
        pr.add_argument('-T', "--no-translations", action="store_true", help="don't collect translations")
        pr.add_argument('-v', "--version", action="store_true", help="version information")
        pr.add_argument('-V', "--verbose", action="store_true", help="verbose mode")
        self.__parser = pr

    def parse(self):
        opts = self.__parser.parse_args()
        if opts.version:
            self.version()
            
        if opts.qmake is None or opts.file is None:
            die("invalid command line arguments! Try -h or --help.")
        return opts

    def version(self):
        global SCRIPT_VERSION
        print("%s: Linux Qt Application Deployment Tool version %s" % (os.path.basename(sys.argv[0]), SCRIPT_VERSION))
        sys.exit(0)

class Dependence:
    def __init__(self, name, path):
        self.name = name
        self.path = path

class Element:
    def __init__(self, filename, relative):
        self.filename = filename
        self.relative = relative
        
class App:
    INSTALL_BIN = "bin"
    INSTALL_LIB = "lib"
    INSTALL_PLUGINS = "plugins"
    INSTALL_TRANSLATIONS = "translations"
    
    SO_EXT_NAME = ".so" # libraries and plugins
    QM_EXT_NAME = '.qm' # translations
    
    QT_INSTALL_LIBS = "QT_INSTALL_LIBS"
    QT_INSTALL_PLUGINS = "QT_INSTALL_PLUGINS"
    QT_INSTALL_TRANSLATIONS = "QT_INSTALL_TRANSLATIONS"
    
    def __init__(self):
        self.opts = CommandLineParser().parse()
        self.vars = self.qmake_query_vars()

    def exec_output(self, *args):
        try:
            r = subprocess.check_output(args).decode("utf-8").splitlines()
        except:
            die("failed to exec: %s" % " ".join(args))
        return r

    def exec(self, *args):
        return self.exec_output(*args)
    
    def info(self, s):
        if self.is_verbose():
            sys.stdout.write("[+] %s\n" % s)
            
    def qmake_query_vars(self):
        r = self.exec(self.opts.qmake, "-query")
        d = dict()
        for x in r:
            v = x.split(":", 1)
            if len(v) == 2:
                d[v[0]] = v[1]
        return d

    def qmake_var(self, name):
        return self.vars.get(name, None)
    
    def find_dependencies(self, filename):
        lib = self.qmake_var(self.QT_INSTALL_LIBS)
        if lib is None:
            return None
            
        r = self.exec("ldd", filename)
        d = dict()
        for s in r:
            ss = s.split("(")[0]
            v = ss.split("=>", 1)
            if len(v) == 2:
                name, path = v[0].strip(), os.path.realpath(v[1].strip())
                if path.startswith(lib):
                    d[name] = Dependence(name, path)
        return d

    def collect_elements_by_ext_name(self, path, ext_name):
        elements = list()
        for root, _, names in os.walk(path):
            for name in names:
                filename = os.path.join(root, name)
                ext = os.path.splitext(filename)[1].lower()
                if ext == ext_name:
                    relative = filename[len(path):]
                    relative = relative.lstrip("/")
                    elements.append(Element(filename, relative))
        return elements
    
    def find_plugins(self, path):
        return self.collect_elements_by_ext_name(path, self.SO_EXT_NAME)
        
    def collect_plugins(self):
        plugin_dir = self.qmake_var(self.QT_INSTALL_PLUGINS)
        if plugin_dir is None:
            return None

        return self.find_plugins(plugin_dir)

    def set_file_exec(self, filename):
        os.chmod(filename, 0o755)
        
    def install_file(self, src, dpath, dst, runable=False):
        filename = os.path.join(self.opts.out, dpath, dst)
        pathname = os.path.dirname(filename)
        self.info("installing file: %s" % src)
        os.makedirs(pathname, 0o777, True)
        shutil.copyfile(src, filename)

        if runable:
            self.set_file_exec(filename)
        
    def write_start_script(self, name):
        global START_SCRIPT
        script = os.path.join(self.opts.out, "%s.sh" % name)
        with open(script, "w") as fp:
            fp.write(START_SCRIPT % (self.INSTALL_LIB, self.INSTALL_BIN))

        self.info("creating start script: %s" % script)
        return script
        
    def setup_input_file(self, filename):
        name = os.path.basename(filename)
        base = os.path.splitext(name)[0]
        script = self.write_start_script(base)
        self.set_file_exec(script)
        self.install_file(self.opts.file, self.INSTALL_BIN, name, True)
        return self.find_dependencies(self.opts.file)
        
    def reset_outdir(self):
        """
        reset output dir if necessary
        """
        if os.path.exists(self.opts.out):
            shutil.rmtree(self.opts.out)
        os.mkdir(self.opts.out)
        
    def has_plugins(self):
        return not self.opts.no_plugins

    def has_libraries(self):
        return not self.opts.no_libraries

    def has_translations(self):
        return not self.opts.no_translations
    
    def is_verbose(self):
        return self.opts.verbose
    
    def install_translations(self, path):
        translations = self.collect_elements_by_ext_name(path, self.QM_EXT_NAME)
        for translation in translations:
            self.install_file(translation.filename, self.INSTALL_TRANSLATIONS, translation.relative)

    def run(self):
        self.info("collect plugins option: %s" % self.has_plugins())
        self.info("collect libraries option: %s" % self.has_libraries())
        self.info("collect translations option: %s" % self.has_translations())
        
        self.reset_outdir()
        
        # collect all plugins (TODO: we could optimize this, such as strip unnecessary plugins)
        plugins = self.collect_plugins()
        if plugins is None:
            die("failed to collect plugins!")

        # copy input file and start script
        # the script refers to: https://doc.qt.io/qt-6/linux-deployment.html
        # return all input file dependencies (the dependencies will be copied to lib folder) 
        deps = self.setup_input_file(self.opts.file)
        if deps is None:
            die("failed to parse deps from file: %s" % self.opts.file)

        # check each plugin dependencies and install plugin files (so only)
        if self.has_plugins() and self.has_libraries():
            for plugin in plugins:
                plugin_deps = self.find_dependencies(plugin.filename)
                if plugin_deps is None:
                    die('failed to parse deps from plugin: %s' % plugin.filename)
                deps.update(plugin_deps)
                self.install_file(plugin.filename, self.INSTALL_PLUGINS, plugin.relative)

        # install all dependencies which are collected from input file and plugins
        if self.has_libraries():
            for dep in deps.values():
                self.install_file(dep.path, self.INSTALL_LIB, dep.name)

        if self.has_translations():
            translation_dir = self.qmake_var(self.QT_INSTALL_TRANSLATIONS)
            self.install_translations(translation_dir)

def linux_only():
    """
    this script is only working on Linux system
    """
    return sys.platform.lower().startswith("linux")

def main():
    if not linux_only():
        die("the script will be only working on Linux system!")
        
    App().run()
    
if __name__ == "__main__":
    main()
    
