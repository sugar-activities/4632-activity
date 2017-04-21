# Copyright (C) 2007, One Laptop Per Child
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
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

from gettext import gettext as _

try:
    from sugar3.graphics.toolbutton import ToolButton
    from sugar3.graphics.toolcombobox import ToolComboBox
    # check first sugar3 because in os883 gi.repository is found but not sugar3
    from gi.repository import Gtk
except ImportError:
    import gtk as Gtk

    from sugar.graphics.toolbutton import ToolButton
    from sugar.graphics.toolcombobox import ToolComboBox


class SearchToolbar(Gtk.Toolbar):
    def __init__(self, activity):
        Gtk.Toolbar.__init__(self)

        self._activity = activity

        self._providercombo = ToolComboBox()

        self.insert(self._providercombo, -1)
        self._providercombo.show()

        search_url = 'http://localhost:' + str(activity.confvars['port']) \
                        + '/search?q=%s'

        default_search_providers = {
            'schoolserver': {
                'order': 3,
                'name':  _('Wiki'),
                'url':   search_url,
                'icon':  'zoom-home'
            },
        }

        self.set_providers(default_search_providers)

        self._entry = Gtk.Entry()
        self._entry.connect('activate', self._entry_activate_cb)

        entry_item = Gtk.ToolItem()
        entry_item.set_expand(True)
        entry_item.add(self._entry)
        self._entry.show()

        self.insert(entry_item, -1)
        entry_item.show()

    def _entry_activate_cb(self, entry):
        k = self._providercombo.combo.get_active_item()[0]
        p = self._providers[k]

        browser = self._activity._get_browser()
        browser.load_uri(p['url'] % entry.props.text)
        browser.grab_focus()

    def _cmp_provider_order(self, a, b):
        return self._providers[a]['order'] - self._providers[b]['order']

    def set_providers(self, providers):
        self._providers = providers

        self._providercombo.combo.remove_all()

        for k in sorted(self._providers.keys(), cmp=self._cmp_provider_order):
            p = self._providers[k]
            self._providercombo.combo.append_item(k, p['name'], p['icon'])

        self._providercombo.combo.set_active(0)
