# Hack until https://github.com/pypa/pip/issues/7953 is fixed
import site
import sys
site.ENABLE_USER_SITE = "--user" in sys.argv[1:]


from setuptools import setup
setup()
