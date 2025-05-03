#https://doi.org/10.5281/zenodo.4417809 https://zenodo.org/records/12779975/files/CLCD_classificationsystem.xlsx?download=1 
colors_dict_clcd_v01_2023_int= {
 #   0: (0, 0, 0, 0),  # No data 
    1: (250, 227, 156),  # Cropland
    2: (68, 111, 51),    # Forest
    3: (51, 160, 44),    # Shrub
    4: (171, 211, 123),  # Grassland
    5: (30, 105, 180),   # Water
    6: (166, 206, 227),  # Snow/Ice
    7: (207, 189, 163),  # Barren
    8: (226, 66, 144),   # Impervious (urban)
    9: (40, 155, 232)    # Wetland
}

legend_dict_clcd_v01_2023 = {
    1: "Cropland",
    2: "Forest",
    3: "Shrub",
    4: "Grassland",
    5: "Water",
    6: "Snow/Ice",
    7: "Barren",
    8: "Impervious",
    9: "Wetland"
}

colors_dict_clcd_v01_2023 = {
    1: (250/255, 227/255, 156/255),  # Cropland
    2: (68/255, 111/255, 51/255),    # Forest
    3: (51/255, 160/255, 44/255),    # Shrub
    4: (171/255, 211/255, 123/255),  # Grassland
    5: (30/255, 105/255, 180/255),   # Water
    6: (166/255, 206/255, 227/255),  # Snow/Ice
    7: (207/255, 189/255, 163/255),  # Barren
    8: (226/255, 66/255, 144/255),   # Impervious
    9: (40/255, 155/255, 232/255)    # Wetland
}

#https://worldcover2021.esa.int/data/docs/WorldCover_PUM_V2.0.pdf p15
colors_dict_esa_worldcover2021_int = {
    #0: (0,0,0,0),              # nodata  
    10: (0, 100, 0),          # Tree cover
    20: (255, 187, 34),       # Shrubland
    30: (255, 255, 76),       # Grassland
    40: (240, 150, 255),      # Cropland
    50: (250, 0, 0),          # Built-up
    60: (180, 180, 180),      # Bare / sparse vegetation
    70: (240, 240, 240),      # Snow and Ice
    80: (0, 100, 200),        # Permanent water bodies
    90: (0, 150, 160),        # Herbaceous wetland
    95: (0, 207, 117),        # Mangroves
    100: (250, 230, 160)      # Moss and lichen
}

colors_dict_esa_worldcover2021 = {
    #0: (0,0,0),              # nodata 
    10: (0.0, 0.39215686, 0.0),  # Tree cover
    20: (1.0, 0.73333333, 0.13333333),  # Shrubland
    30: (1.0, 1.0, 0.29803922),  # Grassland
    40: (0.94117647, 0.58823529, 1.0),  # Cropland
    50: (0.98039216, 0.0, 0.0),  # Built-up
    60: (0.70588235, 0.70588235, 0.70588235),  # Bare / sparse vegetation
    70: (0.94117647, 0.94117647, 0.94117647),  # Snow and Ice
    80: (0.0, 0.39215686, 0.78431373),  # Permanent water bodies
    90: (0.0, 0.58823529, 0.62745098),  # Herbaceous wetland
    95: (0.0, 0.81176471, 0.45882353),  # Mangroves
    100: (0.98039216, 0.90196078, 0.62745098)  # Moss and lichen
}


legend_dict_esa_worldcover2021 = {
    #0: 'no data',
    10: 'Tree cover',
    20: 'Shrubland',
    30: 'Grassland',
    40: 'Cropland',
    50: 'Built-up',
    60: 'Bare / sparse vegetation',
    70: 'Snow and Ice',
    80: 'Permanent water bodies',
    90: 'Herbaceous wetland',
    95: 'Mangroves',
    100: 'Moss and lichen'
}




#Copernicus Global Land Service: Land Cover 100m: collection 3: epoch 2019: Globe 
#downloaded from zenodo: https://zenodo.org/records/3939050

#original url?: https://land.copernicus.eu/en/products/global-dynamic-land-cover/copernicus-global-land-service-land-cover-100m-collection-3-epoch-2018-globe
#product user manual with legends: https://land.copernicus.eu/en/technical-library/global-dynamic-land-cover-product-user-manual-v3.0/@@download/file

colors_dict_copernicus_global_coll3_int = {
    255: (40, 40, 40, 0),        # No input data available
    111: (88, 72, 31),        # Closed forest, evergreen needle leaf
    113: (112, 102, 62),      # Closed forest, deciduous needle leaf
    112: (0, 153, 0),         # Closed forest, evergreen, broad leaf
    114: (0, 204, 0),         # Closed forest, deciduous broad leaf
    115: (78, 117, 31),       # Closed forest, mixed
    116: (0, 120, 0),         # Closed forest, unknown
    121: (102, 96, 0),        # Open forest, evergreen needle leaf
    123: (141, 116, 0),       # Open forest, deciduous needle leaf
    122: (141, 180, 0),       # Open forest, evergreen broad leaf
    124: (160, 220, 0),       # Open forest, deciduous broad leaf
    125: (146, 153, 0),       # Open forest, mixed
    126: (100, 140, 0),       # Open forest, unknown
    20: (255, 187, 34),       # Shrubs
    30: (255, 255, 76),       # Herbaceous vegetation
    90: (0, 150, 160),        # Herbaceous wetland
    100: (250, 230, 160),     # Moss and lichen
    60: (180, 180, 180),      # Bare / sparse vegetation
    40: (240, 150, 255),      # Cultivated and managed vegetation/agriculture (cropland)
    50: (255, 0, 0),          # Urban / built up
    70: (240, 240, 240),      # Snow and Ice
    80: (0, 50, 200),         # Permanent water bodies
    200: (0, 0, 128)          # Open sea
}

colors_dict_copernicus_global_coll3 = {
    255: (0.15686275, 0.15686275, 0.15686275, 0),  # No input data available
    111: (0.34509804, 0.28235294, 0.12156863),  # Closed forest, evergreen needle leaf
    113: (0.43921569, 0.4, 0.24313725),  # Closed forest, deciduous needle leaf
    112: (0.0, 0.6, 0.0),  # Closed forest, evergreen, broad leaf
    114: (0.0, 0.8, 0.0),  # Closed forest, deciduous broad leaf
    115: (0.30588235, 0.45882353, 0.12156863),  # Closed forest, mixed
    116: (0.0, 0.47058824, 0.0),  # Closed forest, unknown
    121: (0.4, 0.37647059, 0.0),  # Open forest, evergreen needle leaf
    123: (0.55294118, 0.45490196, 0.0),  # Open forest, deciduous needle leaf
    122: (0.55294118, 0.70588235, 0.0),  # Open forest, evergreen broad leaf
    124: (0.62745098, 0.8627451, 0.0),  # Open forest, deciduous broad leaf
    125: (0.57254902, 0.6, 0.0),  # Open forest, mixed
    126: (0.39215686, 0.54901961, 0.0),  # Open forest, unknown
    20: (1.0, 0.73333333, 0.13333333),  # Shrubs
    30: (1.0, 1.0, 0.29803922),  # Herbaceous vegetation
    90: (0.0, 0.58823529, 0.62745098),  # Herbaceous wetland
    100: (0.98039216, 0.90196078, 0.62745098),  # Moss and lichen
    60: (0.70588235, 0.70588235, 0.70588235),  # Bare / sparse vegetation
    40: (0.94117647, 0.58823529, 1.0),  # Cultivated and managed vegetation/agriculture (cropland)
    50: (1.0, 0.0, 0.0),  # Urban / built up
    70: (0.94117647, 0.94117647, 0.94117647),  # Snow and Ice
    80: (0.0, 0.19607843, 0.78431373),  # Permanent water bodies
    200: (0.0, 0.0, 0.50196078)  # Open sea
}

legend_dict_copernicus_global_coll3 = {
    255: 'No input data available',
    111: 'Closed forest, evergreen needle leaf',
    113: 'Closed forest, deciduous needle leaf',
    112: 'Closed forest, evergreen, broad leaf',
    114: 'Closed forest, deciduous broad leaf',
    115: 'Closed forest, mixed',
    116: 'Closed forest, unknown',
    121: 'Open forest, evergreen needle leaf',
    123: 'Open forest, deciduous needle leaf',
    122: 'Open forest, evergreen broad leaf',
    124: 'Open forest, deciduous broad leaf',
    125: 'Open forest, mixed',
    126: 'Open forest, unknown',
    20: 'Shrubs',
    30: 'Herbaceous vegetation',
    90: 'Herbaceous wetland',
    100: 'Moss and lichen',
    60: 'Bare / sparse vegetation',
    40: 'Cultivated and managed vegetation/agriculture (cropland)',
    50: 'Urban / built up',
    70: 'Snow and Ice',
    80: 'Permanent water bodies',
    200: 'Open sea'
}



# CLC Europe 2012

colors_dict_Corine_Europe_2012_int = {
    1: (230, 0, 77),
    2: (255, 0, 0),
    3: (204, 77, 242),
    4: (204, 0, 0),
    5: (230, 204, 204),
    6: (230, 204, 230),
    7: (166, 0, 204),
    8: (166, 77, 0),
    9: (255, 77, 255),
    10: (255, 166, 255),
    11: (255, 230, 255),
    12: (255, 255, 168),
    13: (255, 255, 0),
    14: (230, 230, 0),
    15: (230, 128, 0),
    16: (242, 166, 77),
    17: (230, 166, 0),
    18: (230, 230, 77),
    19: (255, 230, 166),
    20: (255, 230, 77),
    21: (230, 204, 77),
    22: (242, 204, 166),
    23: (128, 255, 0),
    24: (0, 166, 0),
    25: (77, 255, 0),
    26: (204, 242, 77),
    27: (166, 255, 128),
    28: (166, 230, 77),
    29: (166, 242, 0),
    30: (230, 230, 230),
    31: (204, 204, 204),
    32: (204, 255, 204),
    33: (0, 0, 0),
    34: (166, 230, 204),
    35: (166, 166, 255),
    36: (77, 77, 255),
    37: (204, 204, 255),
    38: (230, 230, 255),
    39: (166, 166, 230),
    40: (0, 204, 242),
    41: (128, 242, 230),
    42: (0, 255, 166),
    43: (166, 255, 230),
    44: (230, 242, 255),
    -128: (255, 255, 255)
}

colors_dict_Corine_Europe_2012 = {
    1: (0.9019607843137255, 0.0, 0.30196078431372547),
    2: (1.0, 0.0, 0.0),
    3: (0.8, 0.30196078431372547, 0.9490196078431372),
    4: (0.8, 0.0, 0.0),
    5: (0.9019607843137255, 0.8, 0.8),
    6: (0.9019607843137255, 0.8, 0.9019607843137255),
    7: (0.6509803921568628, 0.0, 0.8),
    8: (0.6509803921568628, 0.30196078431372547, 0.0),
    9: (1.0, 0.30196078431372547, 1.0),
    10: (1.0, 0.6509803921568628, 1.0),
    11: (1.0, 0.9019607843137255, 1.0),
    12: (1.0, 1.0, 0.6588235294117647),
    13: (1.0, 1.0, 0.0),
    14: (0.9019607843137255, 0.9019607843137255, 0.0),
    15: (0.9019607843137255, 0.5019607843137255, 0.0),
    16: (0.9490196078431372, 0.6509803921568628, 0.30196078431372547),
    17: (0.9019607843137255, 0.6509803921568628, 0.0),
    18: (0.9019607843137255, 0.9019607843137255, 0.30196078431372547),
    19: (1.0, 0.9019607843137255, 0.6509803921568628),
    20: (1.0, 0.9019607843137255, 0.30196078431372547),
    21: (0.9019607843137255, 0.8, 0.30196078431372547),
    22: (0.9490196078431372, 0.8, 0.6509803921568628),
    23: (0.5019607843137255, 1.0, 0.0),
    24: (0.0, 0.6509803921568628, 0.0),
    25: (0.30196078431372547, 1.0, 0.0),
    26: (0.8, 0.9490196078431372, 0.30196078431372547),
    27: (0.6509803921568628, 1.0, 0.5019607843137255),
    28: (0.6509803921568628, 0.9019607843137255, 0.30196078431372547),
    29: (0.6509803921568628, 0.9490196078431372, 0.0),
    30: (0.9019607843137255, 0.9019607843137255, 0.9019607843137255),
    31: (0.8, 0.8, 0.8),
    32: (0.8, 1.0, 0.8),
    33: (0.0, 0.0, 0.0),
    34: (0.6509803921568628, 0.9019607843137255, 0.8),
    35: (0.6509803921568628, 0.6509803921568628, 1.0),
    36: (0.30196078431372547, 0.30196078431372547, 1.0),
    37: (0.8, 0.8, 1.0),
    38: (0.9019607843137255, 0.9019607843137255, 1.0),
    39: (0.6509803921568628, 0.6509803921568628, 0.9019607843137255),
    40: (0.0, 0.8, 0.9490196078431372),
    41: (0.5019607843137255, 0.9490196078431372, 0.9019607843137255),
    42: (0.0, 1.0, 0.6509803921568628),
    43: (0.6509803921568628, 1.0, 0.9019607843137255),
    44: (0.9019607843137255, 0.9490196078431372, 1.0),
    -128: (1.0, 1.0, 1.0)
}


legend_dict_Corine_Europe_2012 ={
    1: "Continuous urban fabric",
    2: "Discontinuous urban fabric",
    3: "Industrial or commercial units",
    4: "Road and rail networks and associated land",
    5: "Port areas",
    6: "Airports",
    7: "Mineral extraction sites",
    8: "Dump sites",
    9: "Construction sites",
    10: "Green urban areas",
    11: "Sport and leisure facilities",
    12: "Non-irrigated arable land",
    13: "Permanently irrigated land",
    14: "Rice fields",
    15: "Vineyards",
    16: "Fruit trees and berry plantations",
    17: "Olive groves",
    18: "Pastures",
    19: "Annual crops associated with permanent crops",
    20: "Complex cultivation patterns",
    21: "Land principally occupied by agriculture with significant areas of natural vegetation",
    22: "Agro-forestry areas",
    23: "Broad-leaved forest",
    24: "Coniferous forest",
    25: "Mixed forest",
    26: "Natural grasslands",
    27: "Moors and heathland",
    28: "Sclerophyllous vegetation",
    29: "Transitional woodland-shrub",
    30: "Beaches - dunes - sands",
    31: "Bare rocks",
    32: "Sparsely vegetated areas",
    33: "Burnt areas",
    34: "Glaciers and perpetual snow",
    35: "Inland marshes",
    36: "Peat bogs",
    37: "Salt marshes",
    38: "Salines",
    39: "Intertidal flats",
    40: "Water courses",
    41: "Water bodies",
    42: "Coastal lagoons",
    43: "Estuaries",
    44: "Sea and ocean",
    -128: "NODATA"
}