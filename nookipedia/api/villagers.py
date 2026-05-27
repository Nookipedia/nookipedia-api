from flask import request, Blueprint

from nookipedia.config import DB_KEYS, VILLAGER_LIMIT
from nookipedia.middlewares import authorize
from nookipedia.cargo import get_villager_list


router = Blueprint("villagers", __name__)

LANG_FIELDS = (
    "villager.no_localization,"
    "villager.engb_name=en_gb,"
    "villager.de_name=de,"
    "villager.es_name=es_eu,"
    "villager.esl_name=es_la,"
    "villager.fr_name=fr_eu,"
    "villager.frq_name=fr_ca,"
    "villager.it_name=it,"
    "villager.ja_name=ja,"
    "villager.ja_name_r=ja_romanized,"
    "villager.ko_name=ko,"
    "villager.ko_name_r=ko_romanized,"
    "villager.nl_name=nl,"
    "villager.ru_name=ru,"
    "villager.ru_name_r=ru_romanized,"
    "villager.zh_name=zh_simplified,"
    "villager.zh_name_r=zh_simplified_romanized,"
    "villager.zht_name=zh_traditional,"
    "villager.zht_name_r=zh_traditional_romanized",
    "villager.test"
)


@router.route("/villagers", methods=["GET"])
def get_villager_all():
    authorize(DB_KEYS, request)

    limit = VILLAGER_LIMIT
    tables = "villager"
    join = ""
    langnames = request.args.get("langnames") == "true"

    if request.args.get("excludedetails") == "true":
        fields = "name"
    elif request.args.get("nhdetails") == "true":
        tables = "villager,nh_villager,nh_house"
        join = "villager._pageName=nh_villager._pageName,villager._pageName=nh_house._pageName"
        fields = "villager.name,villager._pageName=url,villager.name,villager.alt_name,villager.title_color,villager.text_color,villager.id,villager.image_url,villager.species,villager.personality,villager.gender,villager.birthday_month,villager.birthday_day,villager.sign,villager.quote,villager.phrase,villager.prev_phrase,villager.prev_phrase2,villager.clothing,villager.islander,villager.debut,villager.dnm,villager.ac,villager.e_plus,villager.ww,villager.cf,villager.nl,villager.wa,villager.nh,villager.film,villager.hhd,villager.pc,nh_villager.image_url=nh_image_url,nh_villager.photo_url=nh_photo_url,nh_villager.icon_url=nh_icon_url,nh_villager.quote=nh_quote,nh_villager.sub_personality=nh_sub-personality,nh_villager.catchphrase=nh_catchphrase,nh_villager.clothing=nh_clothing,nh_villager.clothing_variation=nh_clothing_variation,nh_villager.fav_style1=nh_fav_style1,nh_villager.fav_style2=nh_fav_style2,nh_villager.fav_color1=nh_fav_color1,nh_villager.fav_color2=nh_fav_color2,nh_villager.hobby=nh_hobby,nh_villager.umbrella=nh_umbrella,nh_house.interior_image_url=nh_house_interior_url,nh_house.exterior_image_url=nh_house_exterior_url,nh_house.wallpaper=nh_wallpaper,nh_house.flooring=nh_flooring,nh_house.music=nh_music,nh_house.music_note=nh_music_note"
        if langnames:
            fields += "," + LANG_FIELDS
    else:
        fields = "name,_pageName=url,alt_name,title_color,text_color,id,image_url,species,personality,gender,birthday_month,birthday_day,sign,quote,phrase,prev_phrase,prev_phrase2,clothing,islander,debut,dnm,ac,e_plus,ww,cf,nl,wa,nh,film,hhd,pc"
        if langnames:
            fields += "," + LANG_FIELDS

    return get_villager_list(limit, tables, join, fields)
