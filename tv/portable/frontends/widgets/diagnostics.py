# Miro - an RSS based video player application
# Copyright (C) 2005-2008 Participatory Culture Foundation
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
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA
#
# In addition, as a special exception, the copyright holders give
# permission to link the code of portions of this program with the OpenSSL
# library.
#
# You must obey the GNU General Public License in all respects for all of
# the code used other than OpenSSL. If you modify file(s) with this
# exception, you may extend this exception to your version of the file(s),
# but you are not obligated to do so. If you do not wish to do so, delete
# this exception statement from your version. If you delete this exception
# statement from all source files in the program, then also delete it here.

"""miro.frontends.widgets.diagnostics -- Code for creating and handling
processing for a diagnostics dialog that helps Miro users help us by 
giving them useful information.

Add new items to the ITEMS variable.
"""

from miro.gtcache import gettext as _

from miro.plat.frontends.widgets import widgetset
from miro.frontends.widgets import widgetutil
from miro.dialogs import BUTTON_OK

from miro import app
from miro import config
from miro import prefs
from miro import util

from miro.plat.utils import getAvailableBytesForMovies

import logging

def open_helper(d):
    def _open_handler(widget):
        app.widgetapp.open_file(d)
    return _open_handler

SEPARATOR = None
OPEN = _("Open")

# The list of (label, data) pairs to display in the diagnostics.
# 
# Note for data that changes over time, stick the calculation in a lambda so
# that the diagnostics dialog shows the most recent calculation.
ITEMS = [
    { "label": _("Movies location:"), 
      "data": config.get(prefs.MOVIES_DIRECTORY), 
      "button_face": OPEN,
      "button_fun": open_helper(config.get(prefs.MOVIES_DIRECTORY)) },

    { "label": _("Icon cache location:"), 
      "data": config.get(prefs.ICON_CACHE_DIRECTORY),
      "button_face": OPEN,
      "button_fun": open_helper(config.get(prefs.ICON_CACHE_DIRECTORY)) },

    { "label": _("Log file location:"),
      "data": config.get(prefs.LOG_PATHNAME),
      "button_face": OPEN,
      "button_fun": open_helper(config.get(prefs.LOG_PATHNAME)) },

    { "label": _("Downloader log file location:"), 
      "data": config.get(prefs.DOWNLOADER_LOG_PATHNAME),
      "button_face": OPEN,
      "button_fun": open_helper(config.get(prefs.DOWNLOADER_LOG_PATHNAME)) },

    { "label": _("Database file location:"), 
      "data": config.get(prefs.SQLITE_PATHNAME),
      "button_face": OPEN,
      "button_fun": open_helper(config.get(prefs.SQLITE_PATHNAME)) },

    SEPARATOR,

    { "label": _("Space free on disk:"), 
      "data": lambda : util.formatSizeForUser(getAvailableBytesForMovies(), "0B", False) }
]

def run_dialog():
    """Displays a diagnostics windows that tells a user how Miro is set
    up on their machine.
    """
    window = widgetset.Dialog(_("Diagnostics"))
    try:
        t = widgetset.Table(3, len(ITEMS))
        t.set_column_spacing(10)
        for row_num, item in enumerate(ITEMS):
            if item is SEPARATOR:
                t.set_cell(widgetset.Label(""), 0, row_num)
                continue

            label = item.get("label")
            lab = widgetset.Label(label)
            lab.set_bold(True)
            t.set_cell(widgetutil.align_left(lab), 0, row_num)

            data = item.get("data")
            if callable(data):
                data = data()
            if not isinstance(data, basestring):
                data = repr(data)
            datalab = widgetset.Label(data)
            t.set_cell(widgetutil.align_left(datalab), 1, row_num)

            if item.get("button_face"):
                b = widgetset.Button(item["button_face"])
                b.set_size(0.85)
                b.connect('clicked', item["button_fun"])
                t.set_cell(widgetutil.align_left(b), 2, row_num)

        window.set_extra_widget(t)
        window.add_button(BUTTON_OK.text)
        window.run()
    finally:
        window.destroy()