# jhbuild - a build script for GNOME 1.x and 2.x
# Copyright (C) 2001-2003  James Henstridge
#
#   module.py: logic for running the build.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import os
import sys
import string

try:
    import xml.dom.minidom
except ImportError:
    raise SystemExit, 'Python xml packages are required but could not be found'

import cvs

_isxterm = os.environ.get('TERM','').find('xterm') >= 0
_boldcode = os.popen('tput bold', 'r').read()
_normal = os.popen('tput sgr0', 'r').read()
user_shell = os.environ.get('SHELL', '/bin/sh')

class _Struct:
    pass

class Package:
    STATE_START = 'start'
    STATE_DONE  = 'done'
    def __init__(self, name, dependencies=[]):
        self.name = name
        self.dependencies = dependencies
    def __repr__(self):
        return "<%s '%s'>" % (self.__class__.__name__, self.name)

    def get_builddir(self, buildscript):
        pass

    def run_state(self, buildscript, state):
        '''run a particular part of the build for this package.

        Returns a tuple of the following form:
          (next-state, error-flag, [other-states])'''
        method = getattr(self, 'do_' + state)
        return method(buildscript)

class CVSModule(Package):
    STATE_CHECKOUT       = 'checkout'
    STATE_FORCE_CHECKOUT = 'force_checkout'
    STATE_CONFIGURE      = 'configure'
    STATE_BUILD          = 'build'
    STATE_INSTALL        = 'install'

    def __init__(self, cvsmodule, checkoutdir=None, revision=None,
                 autogenargs='', dependencies=[], cvsroot=None):
        Package.__init__(self, checkoutdir or cvsmodule, dependencies)
        self.cvsmodule   = cvsmodule
        self.checkoutdir = checkoutdir
        self.revision    = revision
        self.autogenargs = autogenargs
        self.cvsroot     = cvsroot

    def get_builddir(self, buildscript):
        return os.path.join(buildscript.config.checkoutroot,
                            self.checkoutdir or self.cvsmodule)

    def do_start(self, buildscript):
        checkoutdir = self.get_builddir(buildscript)
        if not buildscript.config.nonetwork: # normal start state
            return (self.STATE_CHECKOUT, None, None)
        elif buildscript.config.nobuild:
            return (self.STATE_DONE, None, None)
        elif not buildscript.config.alwaysautogen and \
                 os.path.exists(os.path.join(checkoutdir, 'Makefile')):
            return (self.STATE_BUILD, None, None)
        else:
            return (self.STATE_CONFIGURE, None, None)

    def do_checkout(self, buildscript, force_checkout=False):
        cvsroot = cvs.CVSRoot(self.cvsroot,
                              buildscript.config.checkoutroot)
        checkoutdir = self.get_builddir(buildscript)
        buildscript.message('checking out %s' % self.name)
        res = cvsroot.update(buildscript, self.cvsmodule,
                             self.revision, self.checkoutdir)

        if buildscript.config.nobuild:
            nextstate = self.STATE_DONE
        elif not buildscript.config.alwaysautogen and \
                 os.path.exists(os.path.join(checkoutdir, 'Makefile')):
            nextstate = self.STATE_BUILD
        else:
            nextstate = self.STATE_CONFIGURE
        # did the checkout succeed?
        if res == 0 and os.path.exists(checkoutdir):
            return (nextstate, None, None)
        else:
            return (nextstate, 'could not update module',
                    [self.STATE_FORCE_CHECKOUT])

    def do_force_checkout(self, buildscript):
        cvsroot = cvs.CVSRoot(self.cvsroot,
                              buildscript.config.checkoutroot)
        checkoutdir = self.get_builddir(buildscript)
        buildscript.message('checking out %s' % self.name)
        res = cvsroot.checkout(buildscript, self.cvsmodule,
                               self.revision, self.checkoutdir)
        if res == 0 and os.path.exists(checkoutdir):
            return (self.STATE_CONFIGURE, None, None)
        else:
            return (self.STATE_CONFIGURE, 'could not checkout module',
                    [self.STATE_FORCE_CHECKOUT])

    def do_configure(self, buildscript):
        checkoutdir = self.get_builddir(buildscript)
        os.chdir(checkoutdir)
        buildscript.message('configuring %s' % self.name)
        cmd = './autogen.sh --prefix %s %s %s' % \
              (buildscript.config.prefix, buildscript.config.autogenargs,
               self.autogenargs)
        if buildscript.execute(cmd) == 0:
            return (self.STATE_BUILD, None, None)
        else:
            return (self.STATE_BUILD, 'could not configure module',
                    [self.STATE_FORCE_CHECKOUT])

    def do_build(self, buildscript):
        os.chdir(self.get_builddir(buildscript))
        buildscript.message('building %s' % self.name)
        cmd = 'make %s' % buildscript.config.makeargs
        if buildscript.execute(cmd) == 0:
            return (self.STATE_INSTALL, None, None)
        else:
            return (self.STATE_INSTALL, 'could not build module',
                    [self.STATE_FORCE_CHECKOUT, self.STATE_CONFIGURE])

    def do_install(self, buildscript):
        os.chdir(self.get_builddir(buildscript))
        buildscript.message('installing %s' % self.name)
        cmd = 'make %s install' % buildscript.config.makeargs
        error = None
        if buildscript.execute(cmd) != 0:
            error = 'could not make module'
        return (self.STATE_DONE, error, [])

class MetaModule(Package):
    def get_builddir(self, buildscript):
        return buildscript.config.checkoutroot
    
    # nothing to actually build in a metamodule ...
    def do_start(self, buildscript):
        return (self.STATE_DONE, None, None)

class MozillaModule(CVSModule):
    def __init__(self, name, autogenargs='', dependencies=[], cvsroot = None):
        CVSModule.__init__(self, name, autogenargs = autogenargs,
			   dependencies = dependencies, cvsroot = cvsroot)
        
    def get_mozilla_ver(self, buildscript):
        filename = os.path.join(self.get_builddir(buildscript),
                                'config', 'milestone.txt')
	fp = open(filename, 'r')
	for line in fp.readlines():
	    if line[0] not in ('#', '\0', '\n'):
                return line[:-1]
        else:
            raise AssertionError

    def checkout(self, buildscript):
        buildscript.message('checking out %s' % self.name)
        os.chdir(buildscript.config.checkoutroot)
        if not os.path.exists(os.path.join('mozilla', 'client.mk')):
            res = buildscript.execute(
                'cvs -z3 -q -d %s checkout -A mozilla/client.mk' %
                self.cvsroot)
            if res != 0:
                raise SystemExit, \
                      "something went wrong while checking out mozilla, please try again later"

        checkoutdir = self.get_builddir(buildscript)
        os.chdir(checkoutdir)
        return buildscript.execute('make -f client.mk checkout')
        
    def do_checkout(self, buildscript, force_checkout=False):
        checkoutdir = self.get_builddir(buildscript)
        if not os.path.exists(os.path.join('Makefile.in')):
            res = self.checkout(buildscript)
        else:
            os.chdir(checkoutdir)
            buildscript.message('updating %s' % self.name)
            res = buildscript.execute('make -f client.mk fast-update')

        if buildscript.config.nobuild:
            nextstate = self.STATE_DONE
        else:
            nextstate = self.STATE_CONFIGURE
            
        # did the checkout succeed?
        if res == 0 and os.path.exists(checkoutdir):
            return (nextstate, None, None)
        else:
            return (nextstate, 'could not update module',
                    [self.STATE_FORCE_CHECKOUT])

    def do_force_checkout(self, buildscript):
        res = self.checkout(buildscript)
        if res == 0:
            return (self.STATE_CONFIGURE, None, None)
        else:
            return (nextstate, 'could not checkout module',
                    [self.STATE_FORCE_CHECKOUT])
        
    def do_configure(self, buildscript):
        checkoutdir = self.get_builddir(buildscript)
        os.chdir(checkoutdir)
        buildscript.message('configuring %s' % self.name)
	mozilla_path = buildscript.config.prefix + '/lib/mozilla-' + \
                       self.get_mozilla_ver(buildscript)
        
        cmd = './configure ' + \
              '--prefix %s ' % buildscript.config.prefix + \
              '%s %s ' % (buildscript.config.autogenargs, self.autogenargs) + \
              '--with-default-mozilla-five-home=%s' % mozilla_path
        
        if not buildscript.execute(cmd):
            return (self.STATE_BUILD, None, None)
        else:
            return (self.STATE_BUILD, 'could not configure module',
                    [self.STATE_FORCE_CHECKOUT])

class Tarball(Package):
    STATE_DOWNLOAD  = 'download'
    STATE_UNPACK    = 'unpack'
    STATE_PATCH     = 'patch'
    STATE_CONFIGURE = 'configure'
    STATE_BUILD     = 'build'
    STATE_INSTALL   = 'install'
    def __init__(self, name, version, source_url, source_size,
                 patches=[], versioncheck=None, dependencies=[]):
        Package.__init__(self, name, dependencies)
        self.version      = version
        self.source_url   = source_url
        self.source_size  = source_size
        self.patches      = []
        self.versioncheck = versioncheck

    def get_builddir(self, buildscript):
        localfile = os.path.basename(self.source_url)
        # strip off packaging extension ...
        if localfile.endswith('.tar.gz'):
            localfile = localfile[:-7]
        elif localfile.endswith('.tar.bz2'):
            localfile = localfile[:-8]
        elif localfile.endswith('.tgz'):
            localfile = localfile[:-4]
        return os.path.join(buildscript.config.checkoutroot, localfile)

    def do_start(self, buildscript):
        # check if jhbuild previously built it ...
        checkoutdir = self.get_builddir(buildscript)
        if os.path.exists(os.path.join(checkoutdir, 'jhbuild-build-stamp')):
            return (self.STATE_DONE, None, None)

        # check if we already have it ...
        if self.versioncheck:
            out = os.popen(self.versioncheck, 'r').read()
            if out and string.find(out, self.version) >= 0:
                return (self.STATE_DONE, None, None)

        return (self.STATE_DOWNLOAD, None, None)

    def do_download(self, buildscript):
        localfile = os.path.join(buildscript.config.checkoutroot,
                                 os.path.basename(self.source_url))
        if not buildscript.config.nonetwork:
            if (not os.path.exists(localfile) or
                os.stat(localfile)[6] != self.source_size):
                buildscript.message('downloading %s' % self.source_url)
                res = buildscript.execute('wget "%s" -O "%s"' %
                                          (self.source_url, localfile))
                if res:
                    return (self.STATE_UNPACK, 'error downloading file', [])

        if not os.path.exists(localfile) or \
               os.stat(localfile)[6] != self.source_size:
            return (self.STATE_UNPACK,
                    'file not downloaded, or of incorrect size', [])
        return (self.STATE_UNPACK, None, None)

    def do_unpack(self, buildscript):
        os.chdir(buildscript.config.checkoutroot)
        localfile = os.path.basename(self.source_url)
        checkoutdir = self.get_builddir(buildscript)

        buildscript.message('unpacking %s' % self.name)
        if localfile.endswith('.bz2'):
            res = buildscript.execute('bunzip2 -dc %s | tar xf -' % localfile)
        elif localfile.endswith('.gz'):
            res = buildscript.execute('gunzip -dc %s | tar xf -' % localfile)
        else:
            raise TypeError, "don't know how to handle: %s" % localfile
        
        if res or not os.path.exists(checkoutdir):
            return (self.STATE_PATCH, 'could not unpack tarball', [])

        return (self.STATE_PATCH, None, None)

    def do_patch(self, buildscript):
        os.chdir(self.get_builddir(buildscript))
        
        for patch in self.patches:
            patchfile = os.path.join(os.path.dirname(__file__), patch[0])
            buildscript.message('applying patch %s' % patch[0])
            res = buildscript.execute('patch -p%d < %s' % (patch[1],patchfile))
            if res:
                return (self.STATE_CONFIGURE, 'could not apply patch', [])
            
        if buildscript.config.nobuild:
            return (self.STATE_DONE, None, None)
        else:
            return (self.STATE_CONFIGURE, None, None)

    def do_configure(self, buildscript):
        os.chdir(self.get_builddir(buildscript))
        buildscript.message('configuring %s' % self.name)
        res = buildscript.execute('./configure --prefix=%s' %
                                  buildscript.config.prefix)
        error = None
        if res != 0:
            error = 'could not configure package'
        return (self.STATE_BUILD, error, [])

    def do_build(self, buildscript):
        os.chdir(self.get_builddir(buildscript))
        buildscript.message('building %s' % self.name)
        cmd = 'make %s' % buildscript.config.makeargs
        if buildscript.execute(cmd) == 0:
            return (self.STATE_INSTALL, None, None)
        else:
            return (self.STATE_INSTALL, 'could not build module', [])

    def do_install(self, buildscript):
        os.chdir(self.get_builddir(buildscript))
        buildscript.message('installing %s' % self.name)
        cmd = 'make %s install' % buildscript.config.makeargs
        error = None
        if buildscript.execute(cmd) != 0:
            error = 'could not make module'
        else:
            open('jhbuild-build-stamp', 'w').write('stamp')
        return (self.STATE_DONE, error, [])

class ModuleSet:
    def __init__(self):
        self.modules = {}
    def add(self, module):
        '''add a Module object to this set of modules'''
        self.modules[module.name] = module
    def addmod(self, *args, **kwargs):
        mod = apply(CVSModule, args, kwargs)
        self.add(mod)

    # functions for handling dep expansion
    def __expand_mod_list(self, modlist, skip):
        '''expands a list of names to a list of Module objects.  Expands
        dependencies.  Does not handle loops in deps''' #"
        ret = [self.modules[modname]
                   for modname in modlist
                       if modname not in skip]
        i = 0
        while i < len(ret):
            depadd = []
            for depmod in [self.modules[modname]
                               for modname in ret[i].dependencies]:
                if depmod not in ret[:i+1] and depmod.name not in skip:
                    depadd.append(depmod)
            if depadd:
                ret[i:i] = depadd
            else:
                i = i + 1
        i = 0
        while i < len(ret):
            if ret[i] in ret[:i]:
                del ret[i]
            else:
                i = i + 1
        return ret

    def get_module_list(self, seed, skip=[]):
        '''gets a list of module objects (in correct dependency order)
        needed to build the modules in the seed list''' #"
        ret = [ self.modules[modname]
                for modname in seed if modname not in skip ]
        i = 0
        while i < len(ret):
            depadd = []
            for depmod in [ self.modules[modname]
                            for modname in ret[i].dependencies ]:
                if depmod not in ret[:i+1] and depmod.name not in skip:
                    depadd.append(depmod)
            if depadd:
                ret[i:i] = depadd
            else:
                i = i + 1
        i = 0
        while i < len(ret):
            if ret[i] in ret[:i]:
                del ret[i]
            else:
                i = i + 1
        return ret
    
    def get_full_module_list(self, skip=[]):
        return self.get_module_list(self.modules.keys(), skip=skip)
    
    def write_dot(self, modules=None, fp=sys.stdout):
        if modules is None:
            modules = self.modules.keys()
        inlist = {}
        for module in modules:
            inlist[module] = None

        fp.write('digraph "G" {\n'
                 '  fontsize = 8;\n'
                 '  ratio = auto;\n')
        while modules:
            modname = modules[0]
            mod = self.modules[modname]
            if isinstance(mod, CVSModule):
                label = mod.cvsmodule
                if mod.revision:
                    label = label + '\\nrv: ' + mod.revision
                attrs = '[color="lightskyblue",style="filled",label="%s"]' % \
                        label
            elif isinstance(mod, MetaModule):
                attrs = '[color="lightcoral",style="filled",' \
                        'label="%s"]' % mod.name
            elif isinstance(mod, Tarball):
                attrs = '[color="lightgoldenrod",style="filled",' \
                        'label="%s\\n%s"]' % (mod.name, mod.version)
            fp.write('  "%s" %s;\n' % (modname, attrs))
            del modules[0]
            
            for dep in self.modules[modname].dependencies:
                fp.write('  "%s" -> "%s";\n' % (modname, dep))
                if not inlist.has_key(dep):
                    modules.append(dep)
                inlist[dep] = None
        fp.write('}\n')

def read_module_set(configdict):
    filename = os.path.join(os.path.dirname(__file__), 'modulesets',
                            configdict['moduleset'] + '.modules')
    document = xml.dom.minidom.parse(filename)
    assert document.documentElement.nodeName == 'moduleset'
    moduleset = ModuleSet()
    branches = configdict.get('branches', {})

    # load up list of cvsroots
    cvsroots = {}
    default_cvsroot = None
    for key in configdict['cvsroots'].keys():
        value = configdict['cvsroots'][key]
        cvs.login(value)
        cvsroots[key] = value
    for node in document.documentElement.childNodes:
        if node.nodeType != node.ELEMENT_NODE: continue
        if node.nodeName == 'cvsroot':
            name = node.getAttribute('name')
            cvsroot = node.getAttribute('root')
            password = None
            is_default = False
            if node.hasAttribute('password'):
                password = node.getAttribute('password')
            if node.hasAttribute('default'):
                is_default = node.getAttribute('default') == 'yes'
            if not cvsroots.has_key(name):
                cvs.login(cvsroot, password)
                cvsroots[name] = cvsroot
            if is_default:
                default_cvsroot = name

    # and now module definitions
    for node in document.documentElement.childNodes:
        if node.nodeType != node.ELEMENT_NODE: continue
        if node.nodeName == 'cvsmodule':
            id = node.getAttribute('id')
            module = id
            revision = None
            checkoutdir = None
            autogenargs = ''
            cvsroot = cvsroots[default_cvsroot]
            dependencies = []
            if node.hasAttribute('module'):
                module = node.getAttribute('module')
            if node.hasAttribute('revision'):
                revision = node.getAttribute('revision')
            if node.hasAttribute('checkoutdir'):
                checkoutdir = node.getAttribute('checkoutdir')
            if node.hasAttribute('autogenargs'):
                autogenargs = node.getAttribute('autogenargs')
            if node.hasAttribute('cvsroot'):
                cvsroot = cvsroots[node.getAttribute('cvsroot')]
            # deps
            for childnode in node.childNodes:
                if childnode.nodeType == childnode.ELEMENT_NODE and \
                       childnode.nodeName == 'dependencies':
                    for dep in childnode.childNodes:
                        if dep.nodeType == dep.ELEMENT_NODE:
                            assert dep.nodeName == 'dep'
                            dependencies.append(dep.getAttribute('package'))
                    break

            # override revision tag if requested.
            if branches.has_key(module):
                revision = branches[module]

            moduleset.add(CVSModule(module, checkoutdir, revision,
                                    autogenargs, cvsroot=cvsroot,
                                    dependencies=dependencies))
        elif node.nodeName == 'mozillamodule':
            name = node.getAttribute('id')
            autogenargs = ''
            cvsroot = cvsroots[default_cvsroot]
            dependencies = []
            if node.hasAttribute('checkoutdir'):
                checkoutdir = node.getAttribute('checkoutdir')
            if node.hasAttribute('autogenargs'):
                autogenargs = node.getAttribute('autogenargs')
            if node.hasAttribute('cvsroot'):
                cvsroot = cvsroots[node.getAttribute('cvsroot')]
            # deps
            for childnode in node.childNodes:
                if childnode.nodeType == childnode.ELEMENT_NODE and \
                       childnode.nodeName == 'dependencies':
                    for dep in childnode.childNodes:
                        if dep.nodeType == dep.ELEMENT_NODE:
                            assert dep.nodeName == 'dep'
                            dependencies.append(dep.getAttribute('package'))
                    break
            moduleset.add(MozillaModule(name, autogenargs, dependencies,
                                        cvsroot))
        elif node.nodeName == 'tarball':
            name = node.getAttribute('id')
            version = node.getAttribute('version')
            versioncheck = None
            source_url = None
            source_size = None
            patches = []
            dependencies = []
            if node.hasAttribute('versioncheck'): versioncheck = node.getAttribute('versioncheck')
            for childnode in node.childNodes:
                if childnode.nodeType != childnode.ELEMENT_NODE: continue
                if childnode.nodeName == 'source':
                    source_url = childnode.getAttribute('href')
                    source_size = int(childnode.getAttribute('size'))
                elif childnode.nodeName == 'patches':
                    for patch in childnode.childNodes:
                        if patch.nodeType == dep.ELEMENT_NODE:
                            assert patch.nodeName == 'patch'
                            text = ''.join([node.data
                                            for node in patch.childNodes
                                            if node.nodeType==node.TEXT_NODE])
                            patch.append(text)
                elif childnode.nodeName == 'dependencies':
                    for dep in childnode.childNodes:
                        if dep.nodeType == dep.ELEMENT_NODE:
                            assert dep.nodeName == 'dep'
                            dependencies.append(dep.getAttribute('package'))
            moduleset.add(Tarball(name, version, source_url, source_size,
                                  patches, versioncheck, dependencies))
        elif node.nodeName == 'metamodule':
            id = node.getAttribute('id')
            dependencies = []
            for childnode in node.childNodes:
                if childnode.nodeType == childnode.ELEMENT_NODE and \
                       childnode.nodeName == 'dependencies':
                    for dep in childnode.childNodes:
                        if dep.nodeType == dep.ELEMENT_NODE:
                            assert dep.nodeName == 'dep'
                            dependencies.append(dep.getAttribute('package'))
                    break
            moduleset.add(MetaModule(id, dependencies=dependencies))
    return moduleset

class BuildScript:
    def __init__(self, configdict, module_list):
        self.modulelist = module_list
        self.module_num = 0

        self.config = _Struct
        self.config.autogenargs = configdict.get('autogenargs',
                                                 '--disable-static ' +
                                                 '--disable-gtk-doc')
        self.config.makeargs = configdict.get('makeargs', '')
        self.config.prefix = configdict.get('prefix', '/opt/gtk2')
        self.config.nobuild = configdict.get('nobuild', False)
        self.config.nonetwork = configdict.get('nonetwork', False)
        self.config.alwaysautogen = configdict.get('alwaysautogen', False)
        self.config.makeclean = configdict.get('makeclean', True)

        self.config.checkoutroot = configdict.get('checkoutroot')
        if not self.config.checkoutroot:
            self.config.checkoutroot = os.path.join(os.environ['HOME'],
                                                    'cvs','gnome')
        assert os.access(self.config.checkoutroot, os.R_OK|os.W_OK|os.X_OK), \
               'checkout root must be writable'
        assert os.access(self.config.prefix, os.R_OK|os.W_OK|os.X_OK), \
               'install prefix must be writable'

    def message(self, msg):
        '''shows a message to the screen'''
        if self.module_num > 0:
            percent = ' [%d/%d]' % (self.module_num, len(self.modulelist))
        else:
            percent = ''
        print '%s*** %s ***%s%s' % (_boldcode, msg, percent, _normal)
        if _isxterm:
            print '\033]0;jhbuild: %s%s\007' % (msg, percent)

    def execute(self, command):
        '''executes a command, and returns the error code'''
        print command
        ret = os.system(command)
        print
        return ret

    def build(self):
        poison = [] # list of modules that couldn't be built

        self.module_num = 0
        for module in self.modulelist:
            self.module_num = self.module_num + 1
            poisoned = 0
            for dep in module.dependencies:
                if dep in poison:
                    self.message('module %s not built due to non buildable %s'
                                 % (module.name, dep))
                    poisoned = True
            if poisoned:
                poison.append(module.name)
                continue

            state = module.STATE_START
            while state != module.STATE_DONE:
                nextstate, error, altstates = module.run_state(self, state)

                if error:
                    newstate = self.handle_error(module, state,
                                                 nextstate, error, altstates)
                    if newstate == 'poison':
                        poison.append(module.name)
                        state = module.STATE_DONE
                    else:
                        state = newstate
                else:
                    state = nextstate
        if len(poison) == 0:
            self.message('success')
        else:
            self.message('the following modules were not built')
            for module in poison:
                print module,
            print

    def handle_error(self, module, state, nextstate, error, altstates):
        '''handle error during build'''
        self.message('error during stage %s of %s: %s' % (state, module.name,
                                                          error))
        while True:
            print
            print '  [1] rerun stage %s' % state
            print '  [2] ignore error and continue to %s' % nextstate
            print '  [3] give up on module'
            print '  [4] start shell'
            i = 5
            for altstate in altstates:
                print '  [%d] go to stage %s' % (i, altstate)
                i = i + 1
            val = raw_input('choice: ')
            val = val.strip()
            if val == '1':
                return state
            elif val == '2':
                return nextstate
            elif val == '3':
                return 'poison'
            elif val == '4':
                os.chdir(module.get_builddir(self))
                print 'exit shell to continue with build'
                os.system(user_shell)
            else:
                try:
                    val = int(val)
                    return altstates[val - 5]
                except:
                    print 'invalid choice'

