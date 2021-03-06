# Miro - an RSS based video player application
# Copyright (C) 2005-2010 Participatory Culture Foundation
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

"""video.py -- Video code. """

import time

import gobject
import gtk
import logging

from miro import app
from miro import player
from miro.gtcache import gettext as _
from miro import signals
from miro import util
from miro import messages
from miro import displaytext
from miro.plat import resources
from miro.plat import screensaver
from miro.frontends.widgets.gtk.window import Window, WrappedWindow
from miro.frontends.widgets.gtk.widgetset import (Widget, VBox, Label, HBox,
                                                  Alignment, Background,
                                                  DrawingArea, ImageSurface,
                                                  Image, CustomButton)
from miro.frontends.widgets.gtk.persistentwindow import PersistentWindow

BLACK = (0.0, 0.0, 0.0)
WHITE = (1.0, 1.0, 1.0)

# Global VideoWidget object.  We re-use so we can re-use our PersistentWindow
video_widget = None

class ClickableLabel(Widget):
    """This is like a label and reimplements many of the Label things, but
    it's an EventBox with a Label child widget.
    """
    def __init__(self, text, size=0.77, color=WHITE):
        Widget.__init__(self)
        self.set_widget(gtk.EventBox())

        self.label = Label(text)

        self._widget.add(self.label._widget)
        self.label._widget.show()
        self._widget.set_above_child(False)
        self._widget.set_visible_window(False)

        self.set_size(size)
        self.set_color(color)

        self.wrapped_widget_connect('button-release-event', self.on_click)
        self.wrapped_widget_connect('enter-notify-event', self.on_enter_notify)
        self.wrapped_widget_connect('leave-notify-event', self.on_leave_notify)
        self.wrapped_widget_connect('unmap', self.on_unmap)
        self.create_signal('clicked')

    def on_click(self, widget, event):
        self.emit('clicked', event)
        return True

    def on_enter_notify(self, widget, event):
        self._widget.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.HAND1))

    def on_leave_notify(self, widget, event):
        if self._widget.window:
            self._widget.window.set_cursor(None)

    def on_unmap(self, widget):
        if self._widget.window:
            self._widget.window.set_cursor(None)

    def set_size(self, size):
        self.label.set_size(size)

    def set_color(self, color):
        self.label.set_color(color)

    def set_text(self, text):
        self.label.set_text(text)

    def hide(self):
        self.label._widget.hide()

    def show(self):
        self.label._widget.show()

class ClickableImageButton(CustomButton):
    def __init__(self, image_path):
        CustomButton.__init__(self)
        self.image = ImageSurface(Image(image_path))

        self.wrapped_widget_connect('enter-notify-event', self.on_enter_notify)
        self.wrapped_widget_connect('leave-notify-event', self.on_leave_notify)
        self.wrapped_widget_connect('button-release-event', self.on_click)

    def size_request(self, layout):
        return self.image.width, self.image.height

    def draw(self, context, layout):
        self.image.draw(context, 0, 0, self.image.width, self.image.height)

    def on_click(self, widget, event):
        self.emit('clicked', event)
        return True

    def on_enter_notify(self, widget, event):
        self._widget.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.HAND1))

    def on_leave_notify(self, widget, event):
        if self._widget.window:
            self._widget.window.set_cursor(None)

class NullRenderer:
    def __init__(self):
        pass

    def reset(self):
        pass

def make_hidden_cursor():
    pixmap = gtk.gdk.Pixmap(None, 1, 1, 1)
    color = gtk.gdk.Color()
    return gtk.gdk.Cursor(pixmap, pixmap, color, color, 0, 0)

def make_label(text, handler, visible=True):
    if visible:
        lab = ClickableLabel(text)
        lab.connect('clicked', handler)
        return lab

    # if the widget isn't visible, then we stick in an empty string--we just
    # need a placeholder so that things don't move around when the item state
    # changes.
    lab = Label("")
    lab.set_size(0.77)
    return lab

def make_image_button(image_path, handler):
    b = ClickableImageButton(resources.path(image_path))
    b.connect('clicked', handler)
    return b

def _align_left(widget, top_pad=0, bottom_pad=0, left_pad=0, right_pad=0):
    """Align left and pad."""
    alignment = Alignment(0, 0, 0, 1)
    alignment.set_padding(top_pad, bottom_pad, left_pad, right_pad)
    alignment.add(widget)
    return alignment

def _align_right(widget, top_pad=0, bottom_pad=0, left_pad=0, right_pad=0):
    """Align right and pad."""
    alignment = Alignment(1, 0, 0, 1)
    alignment.set_padding(top_pad, bottom_pad, left_pad, right_pad)
    alignment.add(widget)
    return alignment

def _align_center(widget, top_pad=0, bottom_pad=0, left_pad=0, right_pad=0):
    """Align center (horizontally) and pad."""
    alignment = Alignment(0.5, 0, 0, 1)
    alignment.set_padding(top_pad, bottom_pad, left_pad, right_pad)
    alignment.add(widget)
    return alignment

def _align_middle(widget, top_pad=0, bottom_pad=0, left_pad=0, right_pad=0):
    """Align center (vertically) and pad."""
    alignment = Alignment(0, 0.5, 0, 0)
    alignment.set_padding(top_pad, bottom_pad, left_pad, right_pad)
    alignment.add(widget)
    return alignment

# Couple of utility functions to grab GTK widgets out of the widget tree for
# fullscreen code
def _videobox_widget():
    return app.widgetapp.window.videobox._widget

def _window():
    """Returns the window used for playback.  This is either the main window
    or the detached window.
    """
    if app.playback_manager.detached_window:
        return app.playback_manager.detached_window._window
    return app.widgetapp.window._window

class VideoOverlay(Window):
    def __init__(self):
        Window.__init__(self, 'Miro Video Overlay')
        self._window.set_transient_for(_window())
        self.vbox = VBox()
        self.set_content_widget(self.vbox)

    def _make_gtk_window(self):
        return WrappedWindow(gtk.WINDOW_POPUP)

    def position_on_screen(self):
        window = self._window
        parent_window = window.get_transient_for()
        screen = parent_window.get_screen()
        monitor = screen.get_monitor_at_window(parent_window.window)
        screen_rect = screen.get_monitor_geometry(monitor)
        my_width, my_height = self.vbox.get_size_request()
        window.set_default_size(my_width, my_height)
        window.resize(screen_rect.width, my_height)
        window.move(screen_rect.x, screen_rect.y + screen_rect.height -
                my_height)

class VideoWidget(Widget):
    def __init__(self, renderer):
        Widget.__init__(self)
        self.set_widget(PersistentWindow())
        self._widget.set_double_buffered(False)
        self._widget.add_events(gtk.gdk.POINTER_MOTION_MASK)
        self._widget.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        renderer.set_widget(self._widget)

    def destroy(self):
        self._widget.destroy()

class Divider(DrawingArea):
    def size_request(self, layout):
        return (1, 25)

    def draw(self, context, layout):
        context.set_line_width(1)
        context.set_color((46.0 / 255.0, 46.0 / 255.0, 46.0 / 255.0))
        context.move_to(0, 0)
        context.rel_line_to(0, context.height)
        context.stroke()

class VideoDetailsWidget(Background):
    def __init__(self):
        Background.__init__(self)
        self.item_info = None
        self.rebuild_video_details()
        self._delete_link = None

    def rebuild_video_details(self):
        # this removes the child widget if there is one
        self.remove()

        if not self.item_info:
            self.add(HBox())
            return

        info = self.item_info

        outer_hbox = HBox(5)

        if not info.is_external:
            if info.expiration_date is not None:
                text = displaytext.expiration_date(info.expiration_date)
                self._expiration_label = Label(text)
                self._expiration_label.set_size(0.77)
                self._expiration_label.set_color((152.0 / 255.0, 152.0 / 255.0, 152.0 / 255.0))
                outer_hbox.pack_start(_align_middle(self._expiration_label))
                outer_hbox.pack_start(_align_middle(Divider(), top_pad=3, bottom_pad=3, left_pad=5, right_pad=5))

            lab = make_label(_("Keep"), self.handle_keep, info.expiration_date is not None)
            outer_hbox.pack_start(_align_middle(lab))
            outer_hbox.pack_start(_align_middle(Divider(), top_pad=3, bottom_pad=3, left_pad=5, right_pad=5))

        self._subtitles_link = make_label(_("Subtitles"),
                                          self.handle_subtitles)
        outer_hbox.pack_start(_align_middle(self._subtitles_link))
        subtitles_image = make_image_button('images/subtitles_down.png',
                                            self.handle_subtitles)
        outer_hbox.pack_start(_align_middle(subtitles_image))

        outer_hbox.pack_start(_align_middle(Divider(), top_pad=3, bottom_pad=3, left_pad=5, right_pad=5))

        self._delete_link = make_label(_("Delete"), self.handle_delete)
        outer_hbox.pack_start(_align_middle(self._delete_link))

        if not info.is_external:
            outer_hbox.pack_start(_align_middle(Divider(), top_pad=3, bottom_pad=3, left_pad=5, right_pad=5))

            self._share_link = make_label(_("Share"), self.handle_share,
                                          info.has_sharable_url)
            outer_hbox.pack_start(_align_middle(self._share_link))
            outer_hbox.pack_start(_align_middle(Divider(), top_pad=3, bottom_pad=3, left_pad=5, right_pad=5))

            if info.commentslink:
                self._permalink_link = make_label(_("Comments"),
                                                  self.handle_commentslink,
                                                  info.commentslink)
            else:
                self._permalink_link = make_label(_("Permalink"),
                                                  self.handle_permalink,
                                                  info.permalink)
            outer_hbox.pack_start(_align_middle(self._permalink_link))

        outer_hbox.pack_start(_align_middle(Divider(), top_pad=3, bottom_pad=3, left_pad=5, right_pad=5))

        if app.playback_manager.is_fullscreen:
            fullscreen_link = make_label(_("Exit fullscreen"),
                                         self.handle_fullscreen)
            outer_hbox.pack_start(_align_middle(fullscreen_link))
            fullscreen_image = make_image_button('images/fullscreen_exit.png',
                                                 self.handle_fullscreen)
            outer_hbox.pack_start(_align_middle(fullscreen_image))
        else:
            fullscreen_link = make_label(_("Fullscreen"),
                                         self.handle_fullscreen)
            outer_hbox.pack_start(_align_middle(fullscreen_link))
            fullscreen_image = make_image_button('images/fullscreen_enter.png',
                                                 self.handle_fullscreen)
            outer_hbox.pack_start(_align_middle(fullscreen_image))

        if app.playback_manager.detached_window is not None:
            popin_link = make_label(_("Pop-in"), self.handle_popin_popout)
            outer_hbox.pack_start(_align_middle(popin_link))
            popin_image = make_image_button('images/popin.png',
                                            self.handle_popin_popout)
            outer_hbox.pack_start(_align_middle(popin_image))
        else:
            popout_link = make_label(_("Pop-out"), self.handle_popin_popout)
            outer_hbox.pack_start(_align_middle(popout_link))
            popout_image = make_image_button('images/popout.png',
                                             self.handle_popin_popout)
            outer_hbox.pack_start(_align_middle(popout_image))

        self.add(_align_right(outer_hbox, left_pad=15, right_pad=15))

    def hide(self):
        self._widget.hide()

    def show(self):
        self._widget.show()

    def handle_fullscreen(self, widget, event=None):
        app.playback_manager.toggle_fullscreen()

    def handle_popin_popout(self, widget, event=None):
        if app.playback_manager.is_fullscreen:
            app.playback_manager.exit_fullscreen()
        app.playback_manager.toggle_detached_mode()

    def handle_keep(self, widget, event):
        messages.KeepVideo(self.item_info.id).send_to_backend()
        self._widget.window.set_cursor(None)

    def handle_delete(self, widget, event):
        item_info = self.item_info
        self.reset()
        app.widgetapp.remove_items([item_info])

    def handle_subtitles(self, widget, event):
        tracks = []
        menu = gtk.Menu()

        tracks = app.video_renderer.get_subtitle_tracks()

        if len(tracks) == 0:
            child = gtk.MenuItem(_("None Available"))
            child.set_sensitive(False)
            child.show()
            menu.append(child)
        else:
            enabled_track = app.video_renderer.get_enabled_subtitle_track()

            first_child = None
            for i, lang in tracks:
                child = gtk.RadioMenuItem(first_child, lang)
                if enabled_track == i:
                    child.set_active(True)
                child.connect('activate', self.handle_subtitle_change, i)
                child.show()
                menu.append(child)
                if first_child == None:
                    first_child = child

            sep = gtk.SeparatorMenuItem()
            sep.show()
            menu.append(sep)

            child = gtk.RadioMenuItem(first_child, _("Disable Subtitles"))
            if enabled_track == -1:
                child.set_active(True)
            child.connect('activate', self.handle_disable_subtitles)
            child.show()
            menu.append(child)

        sep = gtk.SeparatorMenuItem()
        sep.show()
        menu.append(sep)

        child = gtk.MenuItem(_("Select a Subtitles file..."))
        child.set_sensitive(True)
        child.connect('activate', self.handle_select_subtitle_file)
        child.show()
        menu.append(child)

        menu.popup(None, None, None, event.button, event.time)

    def handle_disable_subtitles(self, widget):
        if widget.active:
            app.video_renderer.disable_subtitles()
            app.widgetapp.window.on_playback_change(app.playback_manager)

    def handle_subtitle_change(self, widget, index):
        if widget.active:
            app.video_renderer.enable_subtitle_track(index)
            app.widgetapp.window.on_playback_change(app.playback_manager)

    def handle_select_subtitle_file(self, widget):
        app.playback_manager.open_subtitle_file()

    def handle_commentslink(self, widget, event):
        app.widgetapp.open_url(self.item_info.commentslink)

    def handle_share(self, widget, event):
        app.widgetapp.share_item(self.item_info)

    def handle_permalink(self, widget, event):
        app.widgetapp.open_url(self.item_info.permalink)

    def update_info(self, item_info):
        self.item_info = item_info
        self.rebuild_video_details()

    def set_video_details(self, item_info):
        """This gets called when the item is set to play.  It should make
        no assumptions about the state of the video details prior to being
        called.
        """
        self.update_info(item_info)

    def draw(self, context, layout):
        context.set_color(BLACK)
        context.rectangle(0, 0, context.width, context.height)
        context.fill()
        context.set_color((46.0 / 255.0, 46.0 / 255.0, 46.0 / 255.0))
        context.set_line_width(1)
        context.move_to(0, 0)
        context.rel_line_to(context.width, 0)
        context.stroke()

    def is_opaque(self):
        return True

    def reset(self):
        if self._delete_link:
            self._delete_link.on_leave_notify(None, None)

class VideoPlayer(player.Player, VBox):
    """Video renderer widget.

    Note: ``app.video_renderer`` must be initialized before instantiating this
    class.  If no renderers can be found, set ``app.video_renderer`` to ``None``.
    """
    HIDE_CONTROLS_TIMEOUT = 2000

    def __init__(self):
        global video_widget
        player.Player.__init__(self)
        VBox.__init__(self)
        if app.video_renderer is not None:
            self.renderer = app.video_renderer
        else:
            self.renderer = NullRenderer()

        self.overlay = None

        if video_widget is None:
            video_widget = VideoWidget(self.renderer)
        self._video_widget = video_widget
        self.pack_start(self._video_widget, expand=True)

        self._video_details = VideoDetailsWidget()
        self.pack_start(self._video_details)

        self.hide_controls_timeout = None
        self.motion_handler = None
        self.videobox_motion_handler = None
        self.hidden_cursor = make_hidden_cursor()
        # piggyback on the TrackItemsManually message that playback.py sends.
        app.info_updater.item_changed_callbacks.add('manual', 'playback-list',
                self._on_items_changed)
        self._item_id = None

        self._video_widget.wrapped_widget_connect('button-press-event', self.on_button_press)

    def teardown(self):
        self.renderer.reset()
        app.info_updater.item_changed_callbacks.remove('manual',
                'playback-list', self._on_items_changed)
        self._items_changed_callback = None
        self.remove(self._video_widget)

    def _on_items_changed(self, message):
        for item_info in message.changed:
            if item_info.id == self._item_id:
                self._video_details.update_info(item_info)
                break

    def update_for_presentation_mode(self, mode):
        pass

    def set_item(self, item_info, success_callback, error_callback):
        self._video_details.set_video_details(item_info)
        self.renderer.select_file(item_info, success_callback, error_callback)
        self._item_id = item_info.id

    def get_elapsed_playback_time(self):
        return self.renderer.get_current_time()

    def get_total_playback_time(self):
        return self.renderer.get_duration()

    def set_volume(self, volume):
        self.renderer.set_volume(volume)

    def play(self):
        self.renderer.play()
        # do this to trigger the overlay showing up for a smidge
        self.on_mouse_motion(None, None)

    def play_from_time(self, resume_time=0):
        # Note: This overrides player.Player's version of play_from_time, but
        # this one seeks directly rather than fiddling with
        # total_playback_time.
        self.seek_to_time(resume_time)
        self.play()

    def pause(self):
        self.renderer.pause()

    def stop(self, will_play_another=False):
        self._video_details.reset()
        self.renderer.stop()

    def set_playback_rate(self, rate):
        self.renderer.set_rate(rate)

    def seek_to(self, position):
        duration = self.get_total_playback_time()
        if duration is None:
            return
        time = duration * position
        self.seek_to_time(time)

    def seek_to_time(self, time_pos):
        self.renderer.set_current_time(time_pos)

    def enter_fullscreen(self):
        self.screensaver_manager = screensaver.create_manager()
        if self.screensaver_manager is not None:
            self.screensaver_manager.disable()
        self.rebuild_video_details()
        self._make_overlay()
        self.motion_handler = self.wrapped_widget_connect(
                'motion-notify-event', self.on_mouse_motion)
        self.videobox_motion_handler = self.overlay._window.connect(
                'motion-notify-event', self.on_mouse_motion)
        if not app.playback_manager.detached_window:
            app.widgetapp.window.menubar.hide()
        self.schedule_hide_controls(self.HIDE_CONTROLS_TIMEOUT)
        # make sure all hide() calls go through, otherwise we get the wrong
        # size on windows (#10810)
        while gtk.events_pending(): 
            gtk.main_iteration()
        _window().fullscreen()

    def _make_overlay(self):
        main_window = app.widgetapp.window
        main_window.main_vbox.remove(main_window.controls_hbox)
        self.overlay = VideoOverlay()
        self.remove(self._video_details)
        self.overlay.vbox.pack_start(self._video_details)
        self.overlay.vbox.pack_start(main_window.controls_hbox)
        self.overlay.position_on_screen()
        self.overlay.show()

    def _destroy_overlay(self):
        main_window = app.widgetapp.window
        self.overlay.vbox.remove(self._video_details)
        self.overlay.vbox.remove(main_window.controls_hbox)
        self.pack_start(self._video_details)
        main_window.main_vbox.pack_start(main_window.controls_hbox)

        self.overlay.destroy()
        self.overlay = None

    def rebuild_video_details(self):
        self._video_details.rebuild_video_details()

    def prepare_switch_to_attached_playback(self):
        gobject.timeout_add(0, self.rebuild_video_details)

    def prepare_switch_to_detached_playback(self):
        gobject.timeout_add(0, self.rebuild_video_details)

    def on_button_press(self, widget, event):
        if event.type == gtk.gdk._2BUTTON_PRESS:
            app.playback_manager.toggle_fullscreen()
            return True
        return False

    def on_mouse_motion(self, widget, event):
        if not self.overlay:
            return
        if not self.overlay.is_visible():
            show_it_all = False

            if event is None:
                show_it_all = True
            else:
                # figures out the monitor that miro is fullscreened on and
                # gets the monitor geometry for that.
                if app.playback_manager.detached_window is not None:
                    gtkwindow = app.playback_manager.detached_window._window
                else:
                    gtkwindow = app.widgetapp.window._window
                gdkwindow = gtkwindow.window
                screen = gtkwindow.get_screen()

                monitor = screen.get_monitor_at_window(gdkwindow)
                monitor_geom = screen.get_monitor_geometry(monitor)
                if event.y > monitor_geom.height - 200:
                    show_it_all = True

            if show_it_all:
                self.show_controls()
            else:
                self.show_mouse()
            self.schedule_hide_controls(self.HIDE_CONTROLS_TIMEOUT)
        else:
            self.last_motion_time = time.time()

    def show_mouse(self):
        _window().window.set_cursor(None)

    def show_controls(self):
        logging.info("show_controls")
        self.show_mouse()
        self.overlay.show()

    def hide_controls(self):
        _window().window.set_cursor(self.hidden_cursor)
        if self.overlay and self.overlay.is_visible():
            self.overlay.close()

    def on_hide_controls_timeout(self):
        # Check if the mouse moved before the timeout
        time_since_motion = int((time.time() - self.last_motion_time) * 1000)
        timeout_left = self.HIDE_CONTROLS_TIMEOUT - time_since_motion
        if timeout_left <= 0:
            self.hide_controls()
            self.hide_controls_timeout = None
        else:
            self.schedule_hide_controls(timeout_left)

    def cancel_hide_controls(self):
        if self.hide_controls_timeout is not None:
            gobject.source_remove(self.hide_controls_timeout)

    def schedule_hide_controls(self, time):
        if self.hide_controls_timeout is not None:
            gobject.source_remove(self.hide_controls_timeout)
        self.hide_controls_timeout = gobject.timeout_add(time,
                self.on_hide_controls_timeout)
        self.last_motion_time = 0

    def exit_fullscreen(self):
        if self.screensaver_manager is not None:
            self.screensaver_manager.enable()
            self.screensaver_manager = None
        app.widgetapp.window.menubar.show()
        self.rebuild_video_details()
        self._video_details.show()
        self._destroy_overlay()
        _window().unfullscreen()
        self._widget.disconnect(self.motion_handler)
        self.cancel_hide_controls()
        _window().window.set_cursor(None)

    def select_subtitle_file(self, sub_path, handle_successful_select):
        app.video_renderer.select_subtitle_file(
            app.playback_manager.get_playing_item(), 
            sub_path,
            handle_successful_select)
        
    def select_subtitle_encoding(self, encoding):
        app.video_renderer.select_subtitle_encoding(encoding)
