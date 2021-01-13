from app import app, db


class Location(db.Model):
    __tablename__ = 'locations'
    _to_expand = ()
    _to_exclude = ('managers', 'meals',)
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    shortname = db.Column(db.String, nullable=False)
    code = db.Column(db.String, nullable=False)
    open = db.Column(db.Boolean, nullable=False)
    occupancy = db.Column(db.Integer)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    address = db.Column(db.String, nullable=False)
    phone = db.Column(db.String, nullable=False)

    managers = db.relationship('Manager', cascade='all,delete', back_populates='location')
    meals = db.relationship('Meal', cascade='all,delete', back_populates='location')


class Manager(db.Model):
    __tablename__ = 'managers'
    _to_expand = ()
    _to_exclude = ('location_id', 'location')
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String, nullable=False)
    email = db.Column(db.String)
    position = db.Column(db.String)

    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'))
    location = db.relationship('Location', back_populates='managers')


class Meal(db.Model):
    __tablename__ = 'meals'
    _to_expand = ()
    _to_exclude = ('location', 'items')
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String, nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String)
    end_time = db.Column(db.String)

    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'))
    location = db.relationship('Location', back_populates='meals')
    items = db.relationship('Item', cascade='all,delete', back_populates='meal')


class Item(db.Model):
    __tablename__ = 'items'
    _to_expand = ()
    _to_exclude = ('meal', 'nutrition')
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String, nullable=False)
    ingredients = db.Column(db.String)
    course = db.Column(db.String)

    vegetarian = db.Column(db.Boolean, default=False)
    vegan = db.Column(db.Boolean, default=False)

    alcohol = db.Column(db.Boolean, default=False)
    nuts = db.Column(db.Boolean, default=False)
    shellfish = db.Column(db.Boolean, default=False)
    peanuts = db.Column(db.Boolean, default=False)
    dairy = db.Column(db.Boolean, default=False)
    egg = db.Column(db.Boolean, default=False)
    pork = db.Column(db.Boolean, default=False)
    fish = db.Column(db.Boolean, default=False)
    soy = db.Column(db.Boolean, default=False)
    wheat = db.Column(db.Boolean, default=False)
    gluten = db.Column(db.Boolean, default=False)
    coconut = db.Column(db.Boolean, default=False)

    meal_id = db.Column(db.Integer, db.ForeignKey('meals.id'))
    meal = db.relationship('Meal', back_populates='items')
    nutrition = db.relationship('Nutrition', cascade='all,delete', uselist=False, back_populates='item')


class Nutrition(db.Model):
    __tablename__ = 'nutrition'
    _to_expand = ()
    _to_exclude = ('item',)
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    portion_size = db.Column(db.String)
    calories = db.Column(db.String)

    total_fat = db.Column(db.String)
    saturated_fat = db.Column(db.String)
    trans_fat = db.Column(db.String)
    cholesterol = db.Column(db.String)
    sodium = db.Column(db.String)
    total_carbohydrate = db.Column(db.String)
    dietary_fiber = db.Column(db.String)
    total_sugars = db.Column(db.String)
    protein = db.Column(db.String)
    vitamin_d = db.Column(db.String)
    vitamin_a = db.Column(db.String)
    vitamin_c = db.Column(db.String)
    calcium = db.Column(db.String)
    iron = db.Column(db.String)
    potassium = db.Column(db.String)

    # Percent Daily Value
    total_fat_pdv = db.Column(db.Integer)
    saturated_fat_pdv = db.Column(db.Integer)
    trans_fat_pdv = db.Column(db.Integer)
    cholesterol_pdv = db.Column(db.Integer)
    sodium_pdv = db.Column(db.Integer)
    total_carbohydrate_pdv = db.Column(db.Integer)
    dietary_fiber_pdv = db.Column(db.Integer)
    total_sugars_pdv = db.Column(db.Integer)
    protein_pdv = db.Column(db.Integer)
    vitamin_d_pdv = db.Column(db.Integer)
    vitamin_a_pdv = db.Column(db.Integer)
    vitamin_c_pdv = db.Column(db.Integer)
    calcium_pdv = db.Column(db.Integer)
    iron_pdv = db.Column(db.Integer)
    potassium_pdv = db.Column(db.Integer)

    item_id = db.Column(db.Integer, db.ForeignKey('items.id'))
    item = db.relationship('Item', back_populates='nutrition')
