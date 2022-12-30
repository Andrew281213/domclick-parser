from dataclasses import dataclass


@dataclass
class Rent:
	platform: str
	link: str
	housing_type: str = None
	price: int = None
	name: str = None
	deposit: int = None
	commission: int = None
	rooms_count: int = None
	total_floors: int = None
	floor: int = None
	total_area: int = None
	living_area: int = None
	kitchen_area: int = None
	repair: str = None
	bathroom: str = None
	is_furniture: bool = None
	is_technique: bool = None
	balcony: int = None
	with_children: bool = None
	with_animals: bool = None
	smoke: bool = None
	address: str = None
	is_owner: bool = None
	description: str = None
	photos: dict = None
	published_at: str = None
