#!/usr/bin/env python
# jhbuild - a build script for GNOME 1.x and 2.x
# Copyright (C) 2001-2004  James Henstridge
#
#   changecvsroot.py: script to alter the CVS root of a working copy
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

def changecvsroot(newroot, *dirs):
    def handle(newroot, dirname, fnames):
        if os.path.basename(dirname) == 'CVS' and 'Root' in fnames:
            fp = open(os.path.join(dirname, 'Root'), 'w')
            fp.write('%s\n' % newroot)
    for dir in dirs:
        os.path.walk(dir, handle, newroot)

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        sys.stderr.write('usage: changecvsroot.py newroot dirs ...\n')
        sys.exit(1)
    changecvsroot(sys.argv[1], *sys.argv[2:])
