from setuptools import find_packages, setup

setup(
    name='garden'
    version='1.0.0'
    packages=find_packages()
    include_package_date=True
    zip_safe=False,
    install_requires=[
        'flask',
    ]
)
