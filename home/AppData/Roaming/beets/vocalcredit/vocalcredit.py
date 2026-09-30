"""Import MusicBrainz vocal relationships without changing artist credits.

Installed locally via pluginpath; no changes to the beets installation.
"""
from beets import config, plugins
from beets.dbcore import types
from beets.util import syspath
from mediafile import (MediaFile, ListMediaField, MP3ListDescStorageStyle,
                       MP3ListPeopleStorageStyle, MP4ListStorageStyle,
                       ListStorageStyle, ASFStorageStyle)


def extract_vocals(data):
    names, ids = [], []
    # beets 2.14 uses normalized JSON; retain compatibility with older payloads.
    relations = data.get('artist_relations', data.get('artist-relation-list', []))
    for relation in relations:
        if relation.get('type') != 'vocal':
            continue
        artist = relation.get('artist', {})
        name = artist.get('name')
        if name and name not in names:
            names.append(name)
        mbid = artist.get('id')
        if mbid and mbid not in ids:
            ids.append(mbid)
    # An absent relationship is not proof that the recording is instrumental.
    # Leave existing credits alone when MusicBrainz has none.
    if not names:
        return {}
    return {'vocalists': names, 'mb_vocalistids': ids}


def write_vocal_tags(path, values):
    """Write just the vocal tags; never export unrelated database metadata."""
    media = MediaFile(syspath(path))
    changed = False
    for name in ('vocalists', 'mb_vocalistids'):
        incoming = values.get(name, [])
        if incoming:
            merged = list(dict.fromkeys([*(getattr(media, name) or []), *incoming]))
            if getattr(media, name) != merged:
                setattr(media, name, merged)
                changed = True
    if changed:
        media.save()
    return changed


class VocalCreditPlugin(plugins.BeetsPlugin):
    item_types = {'vocalists': types.MULTI_VALUE_DSV,
                  'mb_vocalistids': types.MULTI_VALUE_DSV}

    def __init__(self):
        super().__init__()
        self.config.add({'auto_write': True})
        self.add_media_field('vocalists', ListMediaField(
            MP3ListDescStorageStyle(desc='VOCALIST'),
            MP3ListPeopleStorageStyle('TMCL', involvement='vocals'),
            MP4ListStorageStyle('----:com.apple.iTunes:VOCALIST'),
            MP4ListStorageStyle('----:com.apple.iTunes:performer:vocals'),
            ListStorageStyle('VOCALIST'),
            ListStorageStyle('PERFORMER:VOCALS'),
            ASFStorageStyle('WM/Vocalist'),
        ))
        self.add_media_field('mb_vocalistids', ListMediaField(
            MP3ListDescStorageStyle(desc='MusicBrainz Vocalist Id'),
            MP4ListStorageStyle('----:com.apple.iTunes:MusicBrainz Vocalist Id'),
            ListStorageStyle('MUSICBRAINZ_VOCALISTID'),
            ASFStorageStyle('MusicBrainz/Vocalist Id'),
        ))
        self.register_listener('mb_track_extract', extract_vocals)
        self.register_listener('item_imported', self.item_imported)
        self.register_listener('album_imported', self.album_imported)

    def item_imported(self, lib, item):
        if self.config['auto_write'].get(bool) and item.get('vocalists'):
            if write_vocal_tags(item.path, item):
                self._log.info('wrote vocal credits: {}', item)

    def album_imported(self, lib, album):
        for item in album.items():
            self.item_imported(lib, item)
