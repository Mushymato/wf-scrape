from lxml import html
import requests
import os
import re
import errno
import aiohttp
import asyncio
import argparse
from PIL import Image, ImageChops
import numpy as np

def merge_path_dir(path):
    new_dir = os.path.dirname(path).replace('/', '_')
    return new_dir + '/' + os.path.basename(path)

def check_target_path(target):
    if not os.path.exists(os.path.dirname(target)):
        try:
            os.makedirs(os.path.dirname(target))
        except OSError as exc: # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise

@asyncio.coroutine
async def download(session, source, target):
    # print('Download', source)
    async with session.get(source) as resp:
        if resp.status == 200:
            check_target_path(target)
            with open(target, 'wb') as f:
                f.write(await resp.read())

path_pattern = re.compile(r'/othermedia/web_other/official/([A-Za-z_0-9]+)/(.*)(\.[a-z]+)')
square = 'https://worldflipper.jp/othermedia/web_other/official/{}/square_0.png'
full_shot = 'https://worldflipper.jp/othermedia/web_other/official/{}/full_shot_0.png'
front = 'https://worldflipper.jp/othermedia/web_other/official/{}/pixelart/front.gif'
special = 'https://worldflipper.jp/othermedia/web_other/official/{}/pixelart/special.gif'

def list_characters(rarity_limit=6):
    characters = set()
    pngs = []
    gifs = []

    for p in range(1, rarity_limit):
        url = 'https://worldflipper.jp/character/?rarity={}'.format(p)
        print(url)
        page = requests.get(url)
        tree = html.fromstring(page.content)
        images = tree.xpath('//img')
        for i in images:
            src = i.get('src')
            res = path_pattern.search(src)
            if not res:
                continue
            name = res.group(1)
            ext = res.group(3)
            target = res.group(2).replace('/', '_') + '/' + name + res.group(3)
            if ext == '.png':
                pngs.append((src, target))
            elif ext == '.gif':
                gifs.append((src, target))
            print(name)
            characters.add(name)

        for name in characters:
            src = full_shot.format(name)
            target = 'full_shot_0/' + name + '.png'
            pngs.append((src, target))

            src = special.format(name)
            target = 'pixelart_special/' + name + '.gif'
            gifs.append((src, target))
    
    return characters, pngs, gifs


async def main_image_dl(images):
    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*[
            download(session, source, target)
            for source, target in images
        ])

def crop_pngs(pngs, override, prefix='processed_'):
    for _, p in pngs:
        if not override and os.path.exists(prefix+p):
            continue
        # image=Image.open(p).convert('RGBA')
        # image.load()
        # imageBox = image.getbbox()
        # rgbImage = image.convert('RGB')
        # croppedBox = rgbImage.getbbox()
        # print(p, imageBox, croppedBox)
        # if imageBox != croppedBox:
        #     cropped = image.crop(croppedBox)
        #     check_target_path(prefix+p)
        #     cropped.save(prefix+p)
        image = Image.open(p)
        image.load()
        bg = Image.new(image.mode, image.size, image.getpixel((0,0)))
        diff = ImageChops.difference(image, bg)
        diff = ImageChops.add(diff, diff, 2.0, -100)
        croppedBox = diff.getbbox()
        if croppedBox:
            print(p, croppedBox)
            cropped = image.crop(croppedBox)
            check_target_path(prefix+p)
            cropped.save(prefix+p)

@asyncio.coroutine
async def crop_gif(g, override, prefix='processed_'):
    if not os.path.exists(g):
        return
    if not override and os.path.exists(prefix+g):
        return
    image=Image.open(g)
    mx1, my1, mx2, my2 = 513, 513, 0, 0
    for frame in range(0, image.n_frames):
        image.seek(frame)
        frame_image = image.convert('RGBA')
        image_data = np.asarray(frame_image)
        image_data_bw = image_data.take(3, axis=2)
        non_empty_columns = np.where(image_data_bw.max(axis=0)>0)[0]
        non_empty_rows = np.where(image_data_bw.max(axis=1)>0)[0]
        x1, y1, x2, y2 = image.getbbox()
        if len(non_empty_columns) > 0:
            x1, x2 = min(non_empty_columns), max(non_empty_columns)+1
        if len(non_empty_rows) > 0:
            y1, y2 = min(non_empty_rows), max(non_empty_rows)+1
        mx1, my1, mx2, my2 = min(x1, mx1), min(y1, my1), max(x2, mx2), max(y2, my2)

    check_target_path(prefix+g)
    cmd = 'gifsicle.exe --crop {},{}-{},{} --output {} {}'.format(mx1, my1, mx2, my2, prefix+g, g)
    os.system(cmd)


async def crop_gifs(gifs, override):
    os.chdir(os.path.abspath('.'))
    await asyncio.gather(*[
        crop_gif(g, override, 'processed_')
        for _, g in gifs
    ])

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Download & Crop World Flipper images.')
    parser.add_argument('-page_limit', type=int, help='number of pages to scrape', default=6)
    parser.add_argument('--skip_dl', help='skip download', dest='skip_dl', action='store_true')
    parser.add_argument('--override', help='override old files', dest='override', action='store_true')

    args = parser.parse_args()

    characters = set()
    pngs = []
    gifs = []
    if args.skip_dl:
        with open('characters.txt', 'r') as f:
            for l in f:
                characters.add(l.strip())
        for c in characters:
            pngs.append((0, 'square_0/' + c + '.png'))
            pngs.append((0, 'full_shot_0/' + c + '.png'))
            gifs.append((0, 'pixelart_front/' + c + '.gif'))
            gifs.append((0, 'pixelart_special/' + c + '.gif'))
    else:
        characters, pngs, gifs = list_characters(args.page_limit)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main_image_dl(pngs+gifs))

        with open('characters.txt', 'w') as f:
            for c in characters:
                f.write(c)
                f.write('\n')
    crop_pngs(pngs, args.override)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(crop_gifs(gifs, args.override))