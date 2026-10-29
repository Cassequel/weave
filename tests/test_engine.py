import base64
import io
import math
import unittest

from PIL import Image, ImageDraw
from pyembroidery import read_pes, COMMAND_MASK, STITCH, COLOR_CHANGE
from engine import convert, pes_bytes


def image_data(image):
    out = io.BytesIO()
    image.save(out, 'PNG')
    return 'data:image/png;base64,' + base64.b64encode(out.getvalue()).decode()


def example():
    image = Image.new('RGBA', (120, 100), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 52, 85), fill='red')
    draw.ellipse((65, 20, 110, 80), fill='blue')
    return image_data(image)


class ConversionTests(unittest.TestCase):
    def settings(self, **overrides):
        return dict({'width': 60, 'height': 50, 'colors': 4, 'removeBackground': True}, **overrides)

    def test_paths_and_pes_readback(self):
        result = convert(example(), self.settings())
        self.assertEqual(len(result['threads']), 2)
        self.assertGreater(result['stitchCount'], 0)
        self.assertEqual(result['stitchCount'], sum(p[2] == 'stitch' for p in result['paths']))
        self.assertTrue(all(0 <= x <= 60 and 0 <= y <= 50 for x, y, _, _ in result['paths']))
        blob = pes_bytes(result)
        self.assertTrue(blob.startswith(b'#PES'))
        pattern = read_pes(io.BytesIO(blob))
        commands = [s[2] & COMMAND_MASK for s in pattern.stitches]
        self.assertIn(STITCH, commands)
        self.assertIn(COLOR_CHANGE, commands)
        self.assertEqual(len(pattern.threadlist), len(result['threads']))

    def test_transparency_and_tiny_features(self):
        image = Image.new('RGBA', (100,100), (0,0,0,0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((10,10,70,70), fill='green')
        draw.point((90,90), fill='red')
        result = convert(image_data(image), self.settings(removeBackground=False, width=50, height=50))
        self.assertTrue(any('removed' in w for w in result['warnings']))

    def test_hoop_and_invalid_data(self):
        for width, height in [(128,178), (0,50), (math.nan,50)]:
            with self.assertRaises(ValueError): convert(example(), self.settings(width=width,height=height))
        with self.assertRaises(ValueError): convert('invalid', self.settings())
        self.assertTrue(convert(example(), self.settings(width=170,height=100))['paths'])

    def test_photograph_like_gradient_and_detail(self):
        image = Image.new('RGB',(120,100))
        for y in range(100):
            for x in range(120): image.putpixel((x,y),(x*2,y*2,(x+y)%256))
        ImageDraw.Draw(image).text((2,2), 'tiny', fill='black')
        result = convert(image_data(image), self.settings(removeBackground=False))
        self.assertGreater(result['stitchCount'],0)
        self.assertLessEqual(len(result['threads']),4)

    def test_custom_thread_color_survives_pes_export(self):
        result = convert(example(), self.settings(threadColors=['#123456']))
        self.assertEqual(result['threads'][0], '#123456')
        pattern = read_pes(io.BytesIO(pes_bytes(result)))
        self.assertEqual(pattern.threadlist[0].color & 0xffffff, 0x123456)

    def test_empty_after_removal(self):
        with self.assertRaisesRegex(ValueError, 'No visible artwork'):
            convert(image_data(Image.new('RGB',(20,20),'white')),self.settings())


if __name__ == '__main__': unittest.main()
