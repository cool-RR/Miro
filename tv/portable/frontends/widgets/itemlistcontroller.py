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

"""itemlistcontroller.py -- Controllers for item lists.

itemlist, itemlistcontroller and itemlistwidgets work togetherusing the MVC
pattern.  itemlist handles the Model, itemlistwidgets handles the View and
itemlistcontroller handles the Controller.

This module contains the ItemListController base class along with controllers
that work for the static tabs which are pretty simple cases.
"""

import itertools
import os
from urlparse import urljoin

from miro import app
from miro import downloader
from miro import messages
from miro import util
from miro.gtcache import gettext as _
from miro.frontends.widgets import dialogs
from miro.frontends.widgets import itemcontextmenu
from miro.frontends.widgets import itemlist
from miro.frontends.widgets import itemlistwidgets
from miro.frontends.widgets import imagepool
from miro.frontends.widgets import widgetutil
from miro.plat.frontends.widgets import widgetset
from miro.plat import resources
from miro.plat.utils import getAvailableBytesForMovies

class ItemListDragHandler(object):
    def allowed_actions(self):
        return widgetset.DRAG_ACTION_COPY

    def allowed_types(self):
        return ('downloaded-item',)

    def begin_drag(self, tableview, rows):
        videos = []
        for row in rows:
            item_info = row[0]
            if item_info.downloaded:
                videos.append(item_info)
        if videos:
            data = '-'.join(str(info.id) for info in videos)
            return {'downloaded-item':  data }
        else:
            return None

class ItemListController(object):
    """Base class for controllers that manage list of items.
    
    Attributes:
        widget -- Widget used to display this controller
    """
    def __init__(self, type, id):
        """Construct a ItemListController.

        type and id are the same as in the constructor to messages.TrackItems
        """
        self.type = type
        self.id = id
        self.current_item_view = None
        self.widget = self.build_widget()
        item_lists = [iv.item_list for iv in self.all_item_views()]
        self.item_list_group = itemlist.ItemListGroup(item_lists)
        self.context_menu_handler = self.make_context_menu_handler()
        context_callback = self.context_menu_handler.callback
        for item_view in self.all_item_views():
            item_view.connect('hotspot-clicked', self.on_hotspot_clicked)
            item_view.connect('selection-changed', self.on_selection_changed)
            item_view.set_context_menu_callback(context_callback)
            item_view.set_drag_source(self.make_drag_handler())
            item_view.set_drag_dest(self.make_drop_handler())

    def get_selection(self):
        """Get the currently selected items.  Returns a list of ItemInfos."""

        item_view = self.current_item_view
        if item_view is None:
            return []
        return [item_view.model[i][0] for i in item_view.get_selection()]

    def play_selection(self):
        """Play the currently selected items."""

        if self.current_item_view is None:
            item_view = self.default_item_view()
        else:
            item_view = self.current_item_view
        selection = self.get_selection()
        if len(selection) == 0:
            items = item_view.item_list.get_items()
        elif len(selection) == 1:
            id = selection[0].id
            items = item_view.item_list.get_items(start_id=id)
        else:
            items = selection
        self._play_item_list(items)

    def _play_item_list(self, items):
        playable = [i for i in items if i.video_path is not None]
        app.playback_manager.start_with_items(playable)

    def on_hotspot_clicked(self, itemview, name, iter):
        """Hotspot handler for ItemViews."""

        item_info, show_details = itemview.model[iter]
        if name == 'download':
            messages.StartDownload(item_info.id).send_to_backend()
        elif name == 'pause':
            messages.PauseDownload(item_info.id).send_to_backend()
        elif name == 'resume':
            messages.ResumeDownload(item_info.id).send_to_backend()
        elif name == 'cancel':
            messages.CancelDownload(item_info.id).send_to_backend()
        elif name == 'keep':
            messages.KeepVideo(item_info.id).send_to_backend()
        elif name == 'delete':
            messages.DeleteVideo(item_info.id).send_to_backend()
        elif name == 'details_toggle':
            itemview.model.update_value(iter, 1, not show_details)
            itemview.model_changed()
        elif name == 'visit_webpage':
            app.widgetapp.open_url(item_info.permalink)
        elif name == 'visit_filelink':
            app.widgetapp.open_url(item_info.file_url)
        elif name == 'visit_license':
            app.widgetapp.open_url(item_info.license)
        elif name == 'show_local_file':
            if not os.path.exists(item_info.video_path):
                basename = os.path.basename(item_info.video_path)
                dialogs.show_message(
                    _("Error Revealing File"),
                    _("The file \"%s\" was deleted "
                      "from outside Miro.") % basename)
            else:
                app.widgetapp.open_file(item_info.video_path)
        elif name.startswith('description-link:'):
            url = name.split(':', 1)[1]
            base_href = widgetutil.get_feed_info(item_info.feed_id).base_href
            app.widgetapp.open_url(urljoin(base_href, url))
        elif name == 'play':
            id = item_info.id
            items = itemview.item_list.get_items(start_id=id)
            self._play_item_list(items)

    def on_selection_changed(self, item_view):
        if (item_view is not self.current_item_view and
                item_view.num_rows_selected() == 0):
            # This is the result of us calling unselect_all() below
            return

        if item_view is not self.current_item_view:
            self.current_item_view = item_view
            for other_view in self.all_item_views():
                if other_view is not item_view:
                    other_view.unselect_all()

        items = self.get_selection()
        app.menu_manager.handle_item_list_selection(items)

    def should_handle_message(self, message):
        """Inspect a ItemList or ItemsChanged message and figure out if it's
        meant for this ItemList.
        """
        return message.type == self.type and message.id == self.id

    def start_tracking(self):
        """Send the message to start tracking items."""
        messages.TrackItems(self.type, self.id).send_to_backend()

    def stop_tracking(self):
        """Send the message to stop tracking items."""
        messages.StopTrackingItems(self.type, self.id).send_to_backend()

    def handle_item_list(self, message):
        """Handle an ItemList message meant for this ItemContainer."""
        self.item_list_group.add_items(message.items)
        for item_view in self.all_item_views():
            item_view.model_changed()
        self.on_initial_list()

    def handle_items_changed(self, message):
        """Handle an ItemsChanged message meant for this ItemContainer."""
        self.item_list_group.remove_items(message.removed)
        self.item_list_group.update_items(message.changed)
        self.item_list_group.add_items(message.added)
        for item_view in self.all_item_views():
            item_view.model_changed()
        self.on_items_changed()

    def on_initial_list(self):
        """Called after we have receieved the initial list of items.

        Subclasses can override this method if they want.
        """
        pass

    def on_items_changed(self):
        """Called after we have changes to items

        Subclasses can override this method if they want.
        """
        pass

    def make_context_menu_handler(self):
        return itemcontextmenu.ItemContextMenuHandler()

    def make_drag_handler(self):
        return ItemListDragHandler()

    def make_drop_handler(self):
        return None

    def build_widget(self):
        """Build the widget for this controller."""
        raise NotImplementedError()

    def all_item_views(self):
        """Return a list of ItemViews used by this controller."""
        raise NotImplementedError()

    def default_item_view(self):
        """ItemView play from if no videos are selected."""
        raise NotImplementedError()

class SimpleItemListController(ItemListController):

    def __init__(self):
        ItemListController.__init__(self, self.type, self.id)

    def build_widget(self):
        widget = itemlistwidgets.ItemContainerWidget()
        self.titlebar = self.make_titlebar()
        self.item_list = itemlist.ItemList()
        self.item_view = itemlistwidgets.ItemView(self.item_list)
        widget.titlebar_vbox.pack_start(self.titlebar)
        widget.content_vbox.pack_start(self.item_view)
        return widget

    def make_titlebar(self):
        icon = self._make_icon()
        titlebar = itemlistwidgets.ItemListTitlebar(self.title, icon)
        titlebar.connect('search-changed', self._on_search_changed)
        return titlebar

    def _on_search_changed(self, widget, search_text):
        self.item_list_group.set_search_text(search_text)

    def all_item_views(self):
        return [self.item_view]

    def default_item_view(self):
        return self.item_view

    def _make_icon(self):
        image_path = resources.path("wimages/%s" % self.image_filename)
        return imagepool.get(image_path)

class DownloadsController(SimpleItemListController):
    type = 'downloads'
    id = None
    image_filename = 'icon-downloading_large.png'
    title = _("Downloads")

    def __init__(self):
        SimpleItemListController.__init__(self)
        self.toolbar = itemlistwidgets.DownloadToolbar()
        self.toolbar.connect("pause-all", self._on_pause_all)
        self.toolbar.connect("resume-all", self._on_resume_all)
        self._update_free_space()
        self.widget.titlebar_vbox.pack_start(self.toolbar)

    def _update_free_space(self):
        self.toolbar.update_free_space(getAvailableBytesForMovies())

    def _on_pause_all(self, widget):
        messages.PauseAllDownloads().send_to_backend()

    def _on_resume_all(self, widget):
        messages.ResumeAllDownloads().send_to_backend()

    def on_items_changed(self):
        self.toolbar.update_downloading_rate(downloader.totalDownRate)
        self.toolbar.update_uploading_rate(downloader.totalUpRate)

class NewController(SimpleItemListController):
    type = 'new'
    id = None
    image_filename = 'icon-new_large.png'
    title = _("New Videos")

class SearchController(SimpleItemListController):
    type = 'search'
    id = None
    image_filename = 'icon-search_large.png'
    title = _("Video Search")


    def make_titlebar(self):
        icon = self._make_icon()
        titlebar = itemlistwidgets.SearchListTitlebar(self.title, icon)
        titlebar.connect('search', self._on_search)
        return titlebar

    def _on_search(self, widget, engine_name, search_text):
        messages.Search(engine_name, search_text).send_to_backend()

class LibraryController(SimpleItemListController):
    type = 'library'
    id = None
    image_filename = 'icon-library_large.png'
    title = _("Library")

class IndividualDownloadsController(SimpleItemListController):
    type = 'individual_downloads'
    id = None
    image_filename = 'icon-individual_large.png'
    title = _("Single Items")