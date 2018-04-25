#!/usr/bin/python

# FIXME: pyexiv2 wants binary in py2
# from __future__ import unicode_literals

import sys
import os

import re
import tempfile
import traceback

import mwparserfromhell as hell
import MySQLdb
import pyexiv2

sys.path.append(os.path.join(os.path.dirname(sys.argv[0]), 'pywikibot-core'))
import pywikibot  # noqa

try:
    unicode
except NameError:  # py3
    unicode = str

# trap broken pyexiv
try:
    pyexiv2.ImageMetadata
except AttributeError:
    import socket
    pywikibot.output(socket.gethostname())
    raise


loc1RE = re.compile(r'\{\{[Ll]ocation[ _]dec\|([^\|]+)\|([^\|\}]+)[\|\}]')

gpsRE = re.compile(r'\{\{(Template:|template:|10:|)[Gg]PS[_ ]EXIF\}\}(\n|)')
# gpsRE = re.compile(r'\{\{Template:[Gg]PS[ _]EXIF\}\}')

latrefRE = re.compile(r'^[NnSs]$')
lonrefRE = re.compile(r'^[EeOoWw]$')

site = pywikibot.Site()

connection = MySQLdb.connect(
    host="commonswiki.labsdb",
    db="commonswiki_p",
    read_default_file="~/replica.my.cnf")
cursor = connection.cursor()
cursor.execute("""\
-- https://quarry.wmflabs.org/query/26631
SELECT page_title
    FROM page
INNER JOIN image
    ON img_name = page_title
LEFT JOIN templatelinks
    ON tl_from = page_id
    AND tl_namespace = 10
    AND tl_title IN ('Location', 'Location_dec')
WHERE page_namespace = 6
    AND (
        img_metadata LIKE '%"GPSAltitude"%' OR
        img_metadata LIKE '%"GPSLatitudeRef"%'
    )

    -- select specific images (debug)
    -- AND page_title IN (
    --    'Chur_de_la_basilique_Saint-Sauveur,_Dinan,_France.jpg')

    -- go over all uploads of a specific user (manual)
    -- AND img_user_text = "Niteshift"

    -- contains no relevant template
    AND tl_from IS NULL

    -- look at images of the last two days
    AND img_timestamp > DATE_FORMAT(NOW() - INTERVAL 2 DAY, '%Y%m%d%H%i%S')
UNION
SELECT page_title
    FROM page, templatelinks, image
WHERE tl_namespace = 10
    AND tl_title = 'GPS_EXIF'
    AND page_id = tl_from
    AND page_namespace = 6
    AND page_title = img_name
;""")

data = cursor.fetchall()
cursor.close()
connection.close()


def num_str(value):
    return ('%.5f' % value).rstrip('0').rstrip('.')


def deg_min_sec(*args):
    deg = 0.0
    for i, element in enumerate(args):
        deg += float(element) / 60**i

    return deg, '|'.join(map(num_str, args))


def extract_exif_latlong(metadata, latlong, posdir, negdir):
    if 'Exif.GPSInfo.GPSLongitude' in metadata.exif_keys:
        dec, params = deg_min_sec(
            *metadata['Exif.GPSInfo.GPS' + latlong].value)
        ref = metadata['Exif.GPSInfo.GPS' + latlong + 'Ref'].value
    else:
        exif = metadata['Xmp.exif.GPS' + latlong].value
        dec, params = deg_min_sec(exif.degrees, exif.minutes, exif.seconds)
        ref = metadata['Xmp.exif.GPS' + latlong].value.direction

    if ref == negdir:
        dec = -dec
    elif ref != posdir:
        raise RuntimeError('Broken %s ref: %s!' % (latlong.lower(), ref))

    return dec, '|' + params + '|' + ref


def already_processed(name, page):
    pywikibot.output("HMM, %s looks already processed" % name)
    page.save("removed gps exif request template")


def process_image(name):
    page = pywikibot.FilePage(site, name.decode('utf-8'))
    page.save = lambda *args, **kwargs: None

    # follow redirects to the actual image page
    while page.isRedirectPage():
        page = page.getRedirectTarget()

    # remove {{GPS EXIF}}
    page.text = gpsRE.sub('', page.text)

    # Location not applicable
    if pywikibot.Category(site, 'Location not applicable') in \
            page.categories():
        pywikibot.output("Location not applicable")
        return

    # already contains a Location
    if '{{Location' in page.text:
        # already contains a generated Location
        if 'source:exif' in page.text:
            return already_processed(name, page)

        # extract location to compare to exif
        lat_in_dec = 0
        lon_in_dec = 0

        # {{Location dec|47.5059|-122.0343|type:forest_region:US}}
        try:
            match = loc1RE.search(page.text)
            lat_in_dec = float(match[0])
            lon_in_dec = float(match[1])
        except TypeError:
            lat_in_dec = 0
            lon_in_dec = 0

    # blocking template
    site.login()  # T153541
    if not page.botMayEdit():
        pywikibot.output("Contains blocking template")
        return

    # already contains a suggestion
    if '<!-- EXIF_BOT' in page.text:
        return already_processed(name, page)

    # check if the metadata contains what we need (TODO)

    with tempfile.NamedTemporaryFile() as downloadfile:
        pywikibot.output("downloading...")
        page.download(downloadfile.name)

        pywikibot.output("analyzing GPS EXIF data ...")

        try:
            metadata = pyexiv2.ImageMetadata(downloadfile.name)
            metadata.read()

            location = '{{Location'

            lat_dec, params = extract_exif_latlong(
                metadata, 'Latitude', 'N', 'S')
            location += params
            lon_dec, params = extract_exif_latlong(
                metadata, 'Longitude', 'E', 'W')
            location += params
        except Exception:
            traceback.print_exc()

            page.save("image does not contain or contains broken GPS data; "
                      "removed gps exif request template")

            return

        #
        # Jump through several hoops to try to determine a heading
        # and make [User:Ikiwaner] happy
        #

        heading = '?'
        try:
            heading = num_str(metadata['Exif.GPSInfo.GPSImgDirection'].value)
            pywikibot.output("Heading found:-)")

        except Exception:
            pywikibot.output("No heading found:-(")

            # try:
            #    heading = num_str(metadata['Exif.GPSInfo.GPSTrack'].value)
            #    pywikibot.output(
            #         "Falling back on direction of movement instead:-/")
            # except Exception:
            #    traceback.print_exc()
            #    pywikibot.output("No dir of movement found either:-(")

        # a lot of cameras create dummy entries with a heading of 0,
        # we do not trust those to be real
        if heading == 0:
            heading = '?'

        #
        # deal with missing altitude data
        #
        try:
            if 'Exif.GPSInfo.GPSAltitude' in metadata.exif_keys:
                alt = metadata['Exif.GPSInfo.GPSAltitude'].value
            else:
                alt = metadata['Xmp.exif.GPSAltitude'].value

            try:
                if int(metadata['Exif.GPSInfo.GPSAltitudeRef'].value) == 1:
                    alt = -alt
            except Exception:
                pywikibot.output("no AltitudeRef, assuming above sea level!")

            location += "|alt:" + num_str(alt) + "_"
        except Exception:
            pywikibot.output("No altitude data")
            location += "|"

        location += 'source:exif_heading:%s}}' % (heading)
        pywikibot.output(location)

        if lon_dec == 0.0 and lat_dec == 0.0:
            raise RuntimeError("apparently INVALID GPS data!")

        #
        # lat or long out of range
        #
        if lat_dec < -90 or lat_dec > 90:
            raise RuntimeError("Lat out of range", lat_dec)

        # pywikibot.output("Old: %f,%f" % (lat_in_dec, lon_in_dec))
        # pywikibot.output("New: %f,%f" % (lat_dec, lon_dec))

        if '{{Location' not in page.text:
            pywikibot.output("YAY! tagging...")

            for template in hell.parse(page.text).filter_templates():
                if (template.name.matches('Information') or
                        template.name.matches('Artwork')):
                    template = unicode(template)
                    assert template in page.text
                    page.text = page.text.replace(
                        template, template + '\n' + location)
                    break
            else:
                page.text = location + '\n' + page.text

            page.save("creating {{Location}} from EXIF data, please visit "
                      "[[Commons:Geocoding]] for further information")
        elif ('<!-- EXIF_BOT' not in page.text and
                'source:exif' not in page.text):
            if (abs(lat_in_dec - lat_dec) < 0.0001 and
                    abs(lon_in_dec - lon_dec) < 0.0001 and
                    (lat_in_dec != 0 or lon_in_dec != 0)):
                pywikibot.output(
                    "OK, existing geocoding seems reasonably accurate")
                return

            # FIXME: Is this supposed to be here or not? commented out in
            # /data/project/gpsexif/gpsexif_bot/gps_exif_bot2.py

            # pywikibot.output("OK, just inserting hidden suggestion")
            # location = (
            #     "%f|%f check EWNS!\n" % (lat_dec, lon_dec)) + location
            # page.text = ('<!-- EXIF_BOT suggests: ' + location +
            #              " -->\n" + page.text)
            # page.save("adding suggested {{Location}} from EXIF data")
        else:
            return already_processed(name, page)


#
# get potential images from taglist
#
for name, in data:
    try:
        pywikibot.output(name)
        process_image(name)
    except Exception:
        traceback.print_exc()
        continue
