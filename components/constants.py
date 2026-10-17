# Copyright 2025 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import mesop as me

NUMBER_OF_IMAGES_OPTIONS = [
    me.SelectOption(label="1", value="1"),
    me.SelectOption(label="2", value="2"),
    me.SelectOption(label="3", value="3"),
    me.SelectOption(label="4", value="4"),
]

ASPECT_RATIO_RADIO_OPTIONS = [
    me.RadioOption(label="1:1", value="1:1"),
    me.RadioOption(label="16:9", value="16:9"),
    me.RadioOption(label="9:16", value="9:16"),
    me.RadioOption(label="4:3", value="4:3"),
    me.RadioOption(label="3:4", value="3:4"),
]

HORIZONTAL_ALIGNMENT_RADIO_OPTIONS = [
    me.RadioOption(label="Left", value="left"),
    me.RadioOption(label="Center", value="center"),
    me.RadioOption(label="Right", value="right"),
]

VERTICAL_ALIGNMENT_RADIO_OPTIONS = [
    me.RadioOption(label="Bottom", value="bottom"),
    me.RadioOption(label="Center", value="center"),
    me.RadioOption(label="Top", value="top"),
]

MASK_MODE_OPTIONS = [
    me.SelectOption(
        label="Foreground",
        value="foreground",
    ),
    me.SelectOption(
        label="Background",
        value="background",
    ),
    me.SelectOption(
        label="Semantic",
        value="semantic",
    ),
    me.SelectOption(
        label="Descriptive",
        value="prompt",
    ),
]

EDIT_MODE_OPTIONS = [
    me.SelectOption(
        label="Insert - Add a new object",
        value="EDIT_MODE_INPAINT_INSERTION",
    ),
    me.SelectOption(
        label="Remove - Erase selected object(s)",
        value="EDIT_MODE_INPAINT_REMOVAL",
    ),
    # me.SelectOption(
    #    label="Product showcase - Place a product in a new scene",
    #    value="EDIT_MODE_PRODUCT_IMAGE",
    # ),
    me.SelectOption(
        label="Product showcase / Change the background.",
        value="EDIT_MODE_BGSWAP",
    ),
    # me.SelectOption(
    #    label="Controlled editing",
    #    value="EDIT_MODE_CONTROLLED_EDITING",
    # ),
]

COMPOSITION_OPTIONS = [
    me.SelectOption(label="None", value="None"),
    me.SelectOption(label="Closeup", value="Closeup"),
    me.SelectOption(label="Knolling", value="Knolling"),
    me.SelectOption(label="Landscape photography", value="Landscape photography"),
    me.SelectOption(
        label="Photographed through window", value="Photographed through window"
    ),
    me.SelectOption(label="Shallow depth of field", value="Shallow depth of field"),
    me.SelectOption(label="Shot from above", value="Shot from above"),
    me.SelectOption(label="Shot from below", value="Shot from below"),
    me.SelectOption(label="Surface detail", value="Surface detail"),
    me.SelectOption(label="Wide angle", value="Wide angle"),
]

LIGHTING_OPTIONS = [
    me.SelectOption(label="None", value="None"),
    me.SelectOption(label="Backlighting", value="Backlighting"),
    me.SelectOption(label="Dramatic light", value="Dramatic light"),
    me.SelectOption(label="Golden hour", value="Golden hour"),
    me.SelectOption(label="Long-time exposure", value="Long-time exposure"),
    me.SelectOption(label="Low lighting", value="Low lighting"),
    me.SelectOption(label="Multiexposure", value="Multiexposure"),
    me.SelectOption(label="Studio light", value="Studio light"),
    me.SelectOption(label="Surreal lighting", value="Surreal lighting"),
]

COLOR_AND_TONE_OPTIONS = [
    me.SelectOption(label="None", value="None"),
    me.SelectOption(label="Black and white", value="Black and white"),
    me.SelectOption(label="Cool tone", value="Cool tone"),
    me.SelectOption(label="Golden", value="Golden"),
    me.SelectOption(label="Monochromatic", value="Monochromatic"),
    me.SelectOption(label="Muted color", value="Muted color"),
    me.SelectOption(label="Pastel color", value="Pastel color"),
    me.SelectOption(label="Toned image", value="Toned image"),
]

CONTENT_TYPE_OPTIONS = [
    me.SelectOption(label="None", value="None"),
    me.SelectOption(label="Photo", value="Photo"),
    me.SelectOption(label="Art", value="Art"),
]

ASPECT_RATIO_OPTIONS = [
    me.SelectOption(label="1:1", value="1:1"),
    me.SelectOption(label="3:4", value="3:4"),
    me.SelectOption(label="4:3", value="4:3"),
    me.SelectOption(label="16:9", value="16:9"),
    me.SelectOption(label="9:16", value="9:16"),
]

SEMANTIC_TYPES = [
    me.SelectOption(label="Airplane", value="airplane"),
    me.SelectOption(label="Animal Other", value="animal_other"),
    me.SelectOption(label="Apple", value="apple"),
    me.SelectOption(label="Apparel", value="apparel"),
    me.SelectOption(label="Arcade Machine", value="arcade_machine"),
    me.SelectOption(label="Armchair", value="armchair"),
    me.SelectOption(label="Autorickshaw", value="autorickshaw"),
    me.SelectOption(label="Awning", value="awning"),
    me.SelectOption(label="Backpack", value="backpack"),
    me.SelectOption(label="Bag", value="bag"),
    me.SelectOption(label="Banana", value="banana"),
    me.SelectOption(label="Banner", value="banner"),
    me.SelectOption(label="Base", value="base"),
    me.SelectOption(label="Baseball Bat", value="baseball_bat"),
    me.SelectOption(label="Baseball Glove", value="baseball_glove"),
    me.SelectOption(label="Basket", value="basket"),
    me.SelectOption(label="Bathtub", value="bathtub"),
    me.SelectOption(label="Bear", value="bear"),
    me.SelectOption(label="Bed", value="bed"),
    me.SelectOption(label="Bicycle", value="bicycle"),
    me.SelectOption(label="Bicyclist", value="bicyclist"),
    me.SelectOption(label="Billboard", value="billboard"),
    me.SelectOption(label="Bike Rack", value="bike_rack"),
    me.SelectOption(label="Bird", value="bird"),
    me.SelectOption(label="Blanket", value="blanket"),
    me.SelectOption(label="Boat Ship", value="boat_ship"),
    me.SelectOption(label="Book", value="book"),
    me.SelectOption(label="Bookshelf", value="bookshelf"),
    me.SelectOption(label="Bottle", value="bottle"),
    me.SelectOption(label="Bowl", value="bowl"),
    me.SelectOption(label="Box", value="box"),
    me.SelectOption(label="Bridge", value="bridge"),
    me.SelectOption(label="Broccoli", value="broccoli"),
    me.SelectOption(label="Building", value="building"),
    me.SelectOption(label="Bulletin Board", value="bulletin_board"),
    me.SelectOption(label="Bus", value="bus"),
    me.SelectOption(label="Cabinet", value="cabinet"),
    me.SelectOption(label="Cake", value="cake"),
    me.SelectOption(label="Car", value="car"),
    me.SelectOption(label="Cabinet", value="cabinet"),
    me.SelectOption(label="Case", value="case"),
    me.SelectOption(label="Cat", value="cat"),
    me.SelectOption(label="Ceiling", value="ceiling"),
    me.SelectOption(label="Cctv Camera", value="cctv_camera"),
    me.SelectOption(label="Chair Other", value="chair_other"),
    me.SelectOption(label="Chandelier", value="chandelier"),
    me.SelectOption(label="Chest Of Drawers", value="chest_of_drawers"),
    me.SelectOption(label="Clock", value="clock"),
    me.SelectOption(label="Column", value="column"),
    me.SelectOption(label="Conveyor Belt", value="conveyor_belt"),
    me.SelectOption(label="Couch", value="couch"),
    me.SelectOption(label="Counter Other", value="counter_other"),
    me.SelectOption(label="Crib", value="crib"),
    me.SelectOption(label="Cup", value="cup"),
    me.SelectOption(label="Curtain Other", value="curtain_other"),
    me.SelectOption(label="Desk", value="desk"),
    me.SelectOption(label="Dishwasher", value="dishwasher"),
    me.SelectOption(label="Dog", value="dog"),
    me.SelectOption(label="Donut", value="donut"),
    me.SelectOption(label="Door", value="door"),
    me.SelectOption(label="Elephant", value="elephant"),
    me.SelectOption(label="Escalator", value="escalator"),
    me.SelectOption(label="Fan", value="fan"),
    me.SelectOption(label="Fence", value="fence"),
    me.SelectOption(label="Fire Hydrant", value="fire_hydrant"),
    me.SelectOption(label="Fireplace", value="fireplace"),
    me.SelectOption(label="Flag", value="flag"),
    me.SelectOption(label="Floor", value="floor"),
    me.SelectOption(label="Food Other", value="food_other"),
    me.SelectOption(label="Fork", value="fork"),
    me.SelectOption(label="Fountain", value="fountain"),
    me.SelectOption(label="Fruit Other", value="fruit_other"),
    me.SelectOption(label="Frisbee", value="frisbee"),
    me.SelectOption(label="Giraffe", value="giraffe"),
    me.SelectOption(label="Gravel", value="gravel"),
    me.SelectOption(label="Guard Rail", value="guard_rail"),
    me.SelectOption(label="Hair Dryer", value="hair_dryer"),
    me.SelectOption(label="Horse", value="horse"),
    me.SelectOption(label="Hot Dog", value="hot_dog"),
    me.SelectOption(label="Junction Box", value="junction_box"),
    me.SelectOption(label="Keyboard", value="keyboard"),
    me.SelectOption(label="Kitchen Island", value="kitchen_island"),
    me.SelectOption(label="Kite", value="kite"),
    me.SelectOption(label="Knife", value="knife"),
    me.SelectOption(label="Lamp", value="lamp"),
    me.SelectOption(label="Laptop", value="laptop"),
    me.SelectOption(label="Light Other", value="light_other"),
    me.SelectOption(label="Mailbox", value="mailbox"),
    me.SelectOption(label="Microwave", value="microwave"),
    me.SelectOption(label="Mirror", value="mirror"),
    me.SelectOption(label="Mouse", value="mouse"),
    me.SelectOption(label="Mountain Hill", value="mountain_hill"),
    me.SelectOption(label="Motorcycle", value="motorcycle"),
    me.SelectOption(label="Motorcyclist", value="motorcyclist"),
    me.SelectOption(label="Net", value="net"),
    me.SelectOption(label="Nightstand", value="nightstand"),
    me.SelectOption(label="Orange", value="orange"),
    me.SelectOption(label="Oven", value="oven"),
    me.SelectOption(label="Painting", value="painting"),
    me.SelectOption(label="Paper", value="paper"),
    me.SelectOption(label="Parking Meter", value="parking_meter"),
    me.SelectOption(label="Person", value="person"),
    me.SelectOption(label="Pier Wharf", value="pier_wharf"),
    me.SelectOption(label="Pillow", value="pillow"),
    me.SelectOption(label="Pizza", value="pizza"),
    me.SelectOption(label="Plate", value="plate"),
    me.SelectOption(label="Platform", value="platform"),
    me.SelectOption(label="Potted Plant", value="potted_plant"),
    me.SelectOption(label="Poster", value="poster"),
    me.SelectOption(label="Pool Table", value="pool_table"),
    me.SelectOption(label="Range Hood", value="range_hood"),
    me.SelectOption(label="Refrigerator", value="refrigerator"),
    me.SelectOption(label="Remote", value="remote"),
    me.SelectOption(label="Road", value="road"),
    me.SelectOption(label="Rock", value="rock"),
    me.SelectOption(label="Rug Floormat", value="rug_floormat"),
    me.SelectOption(label="Sheep", value="sheep"),
    me.SelectOption(label="Shower", value="shower"),
    me.SelectOption(label="Sink", value="sink"),
    me.SelectOption(label="Skateboard", value="skateboard"),
    me.SelectOption(label="Ski", value="ski"),
    me.SelectOption(label="Snow", value="snow"),
    me.SelectOption(label="Stage", value="stage"),
    me.SelectOption(label="Stairs", value="stairs"),
    me.SelectOption(label="Storage Tank", value="storage_tank"),
    me.SelectOption(label="Stove", value="stove"),
    me.SelectOption(label="Sunglasses", value="sunglasses"),
    me.SelectOption(label="Surfboard", value="surfboard"),
    me.SelectOption(label="Swivel Chair", value="swivel_chair"),
    me.SelectOption(label="Table", value="table"),
    me.SelectOption(label="Toilet", value="toilet"),
    me.SelectOption(label="Towel", value="towel"),
    me.SelectOption(label="Train", value="train"),
    me.SelectOption(label="Vase", value="vase"),
    me.SelectOption(label="Vegetation", value="vegetation"),
    me.SelectOption(label="Wardrobe", value="wardrobe"),
    me.SelectOption(label="Washer Dryer", value="washer_dryer"),
    me.SelectOption(label="Whiteboard", value="whiteboard"),
    me.SelectOption(label="Window", value="window"),
    me.SelectOption(label="Zebra", value="zebra"),
]

REFERENCE_TYPES_OPTIONS = [
    me.ButtonToggleButton(
        label="Person",
        value="person",
    ),
    me.ButtonToggleButton(
        label="Animal",
        value="animal",
    ),
    me.ButtonToggleButton(
        label="Product",
        value="product",
    ),
    me.ButtonToggleButton(
        label="Style",
        value="style",
    ),
    me.ButtonToggleButton(
        label="Default",
        value="default",
    ),
]