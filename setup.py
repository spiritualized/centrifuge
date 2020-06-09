from distutils.core import setup
setup(
    name='centrifuge-manager',
    scripts=['centrifuge', 'centrifuge.bat'],
    packages=['.'],
    version='1.0.1',
    description="""Music release management application, which provides metadata validation, repair, and 
    standardization. Useful for managing large libraries.""",
    url='https://github.com/spiritualized/centrifuge',
    download_url='https://github.com/spiritualized/centrifuge/archive/v1.0.1.tar.gz',
    keywords=['audio', 'library', 'management', 'metadata', 'validation', 'mp3', 'flac', 'python'],
    install_requires=[
        'bitstring==3.1.6',
        'cleartag>=1.2.1',
        'colored==1.4.2',
        'lastfmcache>=1.2.3',
        'metafix>=1.2.1',
        'mutagen==1.44.0',
        'ordered-set==3.1.1',
        'release-dir-scanner>=1.0.0'
    ],
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'Programming Language :: Python :: 3.6',
    ],
)
