import json
import os
import sys
from datetime import datetime
from json import JSONDecodeError
from time import sleep

import requests
from fake_useragent import UserAgent
from loguru import logger
from selenium.webdriver.common.by import By
from seleniumwire import undetected_chromedriver as uc
from tqdm import tqdm

from utils import Rent

ATTEMPTS = 3  # Кол-во попыток получения ответа
RESULT_FILENAME = "data.json"  # Название файла результата
TIMEOUT = 20  # Время ожидания ответа

curr_dir = os.path.dirname(os.path.realpath(__file__))
ua = UserAgent()
logger.remove()
logger.add(sys.stdout, level="INFO")
logger.add(os.path.join(curr_dir, "debug.log"), level="DEBUG", rotation="20 MB", retention=0)
urls = [
	"https://offers-service.domclick.ru/research/v5/offers/?address=2787f1cb-a204-46ba-946b-eadf10e43782&offset={offset}&limit=20&sort=qi&sort_dir=desc&deal_type=rent&category=living&offer_type=flat&offer_type=room",
	"https://offers-service.domclick.ru/research/v5/offers/?address=2787f1cb-a204-46ba-946b-eadf10e43782&offset={offset}&limit=20&sort=qi&sort_dir=desc&deal_type=rent&category=living&offer_type=townhouse&offer_type=house_part&offer_type=house"
]
HEADERS = None


def request(url):
	"""Отправка запроса на сервер

	:param str url: Ссылка
	:return: Ответ сервера или None
	:rtype: dict | None
	"""
	for i in range(ATTEMPTS):
		try:
			logger.debug(f"<GET {i} {url}")
			r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
			if r.status_code == 200:
				return r.json()
		except Exception as e:
			logger.debug(f"<GET {i} failed {url}, {e}")
			sleep(3)
	return None


def _parse_links(url):
	"""Сбор ссылок на странице выдачи объявлений

	:param str url: Ссылка на страницу выдачи объявлений
	:return: Список ссылок на объявления и номер максимально страницы
	:rtype: tuple[list, str | None]
	"""
	data = []
	page_data = request(url)
	if page_data is None:
		logger.warning(f"Не удалось получить данные {url}")
		return []
	for item in page_data.get("result", {}).get("items", []):
		link = f"https://yuzhno-saxalinsk.domclick.ru/card/{item['deal_type']}__{item['offer_type']}__{item['id']}"
		ad = Rent(platform="domclick", link=link)
		ad.price = item.get("price_info", {}).get("price")
		ad.address = item.get("address", {}).get("display_name")
		ad.total_floors = item.get("house", {}).get("floors")
		ad.description = item.get("description")
		tmp = item.get("published_dt", "").split("T")[0]
		ad.published_at = datetime.strptime(tmp, "%Y-%m-%d").strftime("%d.%m.%Y")
		tmp = item.get("offer_type")
		if tmp == "room":
			ad.housing_type = "Комната"
		elif tmp == "flat":
			ad.housing_type = "Квартира"
		elif tmp in ("townhouse", "house"):
			ad.housing_type = "Дом"
		ad.total_area = item.get("object_info", {}).get("area")
		ad.floor = item.get("object_info", {}).get("floor")
		ad.is_owner = item.get("legal_options", {}).get("is_owner")
		imgs = item.get("photos", [])
		imgs = ["https://img.dmclk.ru/s1200x800q80" + img.get("url") for img in imgs]
		ad.photos = [{"link": img} for img in imgs]
		data.append(ad)
	return data, page_data.get("pagination", {}).get("total", 0)


def get_headers():
	"""Получения заголовков"""
	global HEADERS
	try:
		logger.debug("Получаю заголовки")
		options = uc.ChromeOptions()
		with uc.Chrome(options=options) as driver:
			driver.get("https://yuzhno-saxalinsk.domclick.ru/search?deal_type=rent&category=living&offer_type=flat")
			sleep(2)
			driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
			driver.find_element(By.XPATH, "//button[contains(@data-test, 'pagination')]").click()
			sleep(5)
			for req in driver.requests:
				if req.url.find("research/v5/offers") > -1:
					if req.headers.get("cookie") is not None:
						HEADERS = req.headers
						logger.debug(f"Получены заголовки: {HEADERS}")
						break
	except Exception as e:
		logger.debug(f"Не удалось получить заголовки {e}")
	if HEADERS is None:
		logger.warning("Не удалось получить заголовки")


def parse_links():
	"""Сбор всех ссылок на объявления с поисковой выдачи

	:return: Список объявлений с основной информацией
	:rtype: list[Rent]
	"""
	data = []
	for url in urls:
		offset = 0
		total = 20
		while offset <= total:
			url = url.format(offset=offset)
			_data, total = _parse_links(url)
			data += _data
			offset += 20
	return data


def get_additional_info(ad):
	"""Получает доп. информацию об объявлениях

	:param Rent ad: Объявление
	"""
	url_parts = ad.link.split("/")[-1].split("__")
	url = f"https://offers-service.domclick.ru/research/v3/offers/{url_parts[0]}/{url_parts[1]}s/{url_parts[2]}"
	page_data = request(url)
	page_data = page_data.get("result")
	if page_data is None:
		logger.warning(f"Не удалось получить информацию {url}")
		return
	obj_info = page_data.get("object_info", {})
	ad.deposit = page_data.get("price_info", {}).get("deposit")
	ad.with_children = page_data.get("rent", {}).get("with_children")
	rooms = obj_info.get("rooms")
	ad.rooms_count = rooms
	if ad.link.find("__flat__") > -1:
		if rooms is not None:
			rooms = f"{rooms}-комнатная"
	elif ad.link.find("__townhouse__") > -1:
		rooms = "таунхаус"
	else:
		rooms = "комната"
	if rooms is None:
		rooms = ""
	ad.name = f"Сдается {rooms}, {ad.total_area} м²"
	ad.kitchen_area = obj_info.get("kitchen_area")
	ad.living_area = obj_info.get("living_area")
	ad.repair = obj_info.get("renovation", {}).get("display_name")
	ad.with_animals = page_data.get("rent", {}).get("with_animals")
	ad.smoke = page_data.get("rent", {}).get("can_smoke")
	amenities = page_data.get("rent", {}).get("amenities", [])
	amenities = [t.get("display_name") for t in amenities]
	if "Мебель на кухне" in amenities or "Мебель в комнатах" in amenities:
		ad.is_furniture = True
	keys = ("Плита", "Микроволновая печь", "Холодильник", "Телевизор", "Стиральная машина")
	for key in keys:
		if key in amenities:
			ad.is_technique = True
			break
	tmp = obj_info.get("connected_bathrooms")
	if tmp is not None:
		ad.bathroom = "Совмещенный" if tmp == 1 else "Раздельный"
	ad.balcony = obj_info.get("balconies")
	ad.commission = page_data.get("price_info", {}).get("commission")


def save(data):
	"""Сохраняет данные в json файл

	:param list[Rent] data: Список данных объявлений
	"""
	logger.info("Сохраняю данные")
	data = [item.__dict__ for item in data]
	filepath = os.path.join(curr_dir, RESULT_FILENAME)
	logger.debug(f"Сохраняю данные в {filepath}")
	try:
		with open(filepath, "w", encoding="utf-8") as file:
			json.dump(data, file, ensure_ascii=False, indent=4)
	except JSONDecodeError as e:
		logger.warning("Не удалось сохранить данные")
		logger.debug(f"{e}")


def parse():
	"""Функция сбора данных из объявлений"""
	logger.info("Начинаю сбор ссылок на объявления")
	get_headers()
	data = []
	try:
		data = parse_links()
		logger.info("Начинаю сбор информации из объявлений")
		for item in tqdm(data):
			try:
				get_additional_info(item)
			except Exception as e:
				logger.warning(f"Не удалось получить данные по объявлению {item.link}")
				logger.debug(f"{e}")
	finally:
		save(data)


if __name__ == '__main__':
	parse()
