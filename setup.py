from distutils.core import setup

setup(
    name="stockanalysis",
    version="0.1",
    description="Stock Analysis Tool",
    long_description="predicts daily stock returns from previous week's stock returns and 8-k form",
    classifiers=[
        "Programming Language :: Python :: 3",
    ],
    url="https://github.com/Evbor/FinTech",
    install_requires=[
    ],
    include_package_data=True,
    author="Evbor",
    author_email="",
    packages=["stockanalysis"]
)