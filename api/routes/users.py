# Author hirata, kosuda
import hashlib

from fastapi import APIRouter, Depends
from typing import List
from starlette.requests import Request

from models.chat_rooms import chat_rooms
from models.user_chat_rooms import user_chat_rooms
from models.users import users
from models.friends import friends
from models.favorites import favorites
from schemas.users import *

from databases import Database

from utils.dbutils import get_connection

from datetime import datetime

router = APIRouter()

# 入力したパスワード（平文）をハッシュ化して返します。
def get_users_insert_dict(user):
    values=user.dict()
    if user.password:
        pwhash=hashlib.sha256(user.password.encode('utf-8')).hexdigest()
        values["hashed_password"]=pwhash
    values.pop("password")
    return values

# usersを全件検索して「UserSelect」のリストをjsonにして返します。
@router.get("/users/", response_model=List[UserDetail])
async def users_findall(request: Request, database: Database = Depends(get_connection)):
    query = users.select()
    return await database.fetch_all(query)

# usersをidで検索して「UserSelect」をjsonにして返します。
@router.get("/users/find", response_model=UserDetail)
async def users_findone(user_id: str, database: Database = Depends(get_connection)):
    query = users.select().where(users.columns.user_id==user_id)
    return await database.fetch_one(query)

@router.post("/users/login", response_model=UserDetail)
async def login_user(req: RequestForLogin, database: Database = Depends(get_connection)):
    query = users.select().where(users.columns.email==req.email)
    user = await database.fetch_one(query)
    user = dict(user)
    if hashlib.sha256(req.password.encode('utf-8')).hexdigest() != user['hashed_password']:
        raise Exception('パスワードが違います')
    return user

@router.post("/users/friends")
async def make_friends(req: RequestForMakeFriends, database: Database = Depends(get_connection)):
    query = users.select().where(users.columns.id==req.user_id)
    user1 = await database.fetch_one(query)
    query = users.select().where(users.columns.id==req.target_user_id)
    user2 = await database.fetch_one(query)
    query = friends.insert()
    values1 = {
        "user_1_id": user1.id,
        "user_2_id": user2.id
    }
    values2 = {
        "user_1_id": user2.id,
        "user_2_id": user1.id
    }
    await database.execute(query, values1)
    await database.execute(query, values2)
    return {"result": "connect success"}

@router.get("/users/friends", response_model=List[UserDetail])
async def get_friends(id: int, database: Database = Depends(get_connection)):
    query = f"select users.* from users left join friends on users.id = friends.user_1_id where friends.user_2_id = {id}"
    return await database.fetch_all(query)

@router.post("/users/favorites")
async def make_favorite(req: RequestForFavorite, database: Database = Depends(get_connection)):
    select_user_query = users.select().where(users.columns.id==req.user_id)
    user = await database.fetch_one(select_user_query)
    select_target_query = users.select().where(users.columns.id==req.target_user_id)
    target_user = await database.fetch_one(select_target_query)
    insert_query = favorites.insert()
    values = {
        "user_id": user.id,
        "target_user_id": target_user.id
    }
    await database.execute(insert_query, values)
    return {"result": "connect success"}

@router.get("/users/favorites", response_model=List[UserDetail])
async def get_favorite(id: int, database: Database = Depends(get_connection)):
    query = f"select users.* from users left join favorites on users.id = favorites.target_user_id where favorites.user_id = {id}"
    return await database.fetch_all(query)

@router.get("/users/recommend", response_model=List[UserDetail])
async def get_recommend(id: int, database: Database = Depends(get_connection)):
    select_user_query = users.select().where(users.columns.id==id)
    user = await database.fetch_one(select_user_query)
    query = f"select users.* from users left join friends on users.id = friends.user_1_id where friends.user_2_id = {id} and status = {user.status} and users.id != {id}"
    return await database.fetch_all(query)

# usersを新規登録します。
@router.post("/users/create")
async def users_create(user: UserCreate, database: Database = Depends(get_connection)):
    # validatorは省略
    select_query = users.select().where(users.columns.user_id==user.user_id)
    user_data = await database.fetch_one(select_query)
    if user_data is not None:
        raise ValueError("This id is already registered.")
    query = users.insert()
    values = get_users_insert_dict(user)
    ret = await database.execute(query, values)
    return {**user.dict()}

# usersを更新します。
@router.post("/users/update", response_model=UserDetail)
async def users_update(user: UserUpdate, database: Database = Depends(get_connection)):
    # validatorは省略
    select_query = users.select().where(users.columns.id==user.id)
    user_data = await database.fetch_one(select_query)
    query = users.update().where(users.columns.id==user.id)
    for k, v in user.dict().items():
        if v == None and hasattr(user_data, k):
            setattr(user, k, getattr(user_data, k))
    values = get_users_insert_dict(user)
    values['status_update_at'] = user_data.status_update_at
    if user.status != user_data.status:
        tdatetime = datetime.now()
        tstr = tdatetime.strftime('%Y/%m/%d')
        values['status_update_at'] = tstr
        # 自動invite
        select_invite_query = f'select * from user_chat_rooms where user_id = {user.id} and valid = 0'
        chat_rooms_data = await database.fetch_all(select_invite_query)
        if not len(chat_rooms_data):
            select_friend_query = f'select users.* from users left join friends on users.id = friends.user_1_id where friends.user_2_id = {user.id} and status = {user.status} and users.id != {user.id}'
            friend = await database.fetch_one(select_friend_query)
            if friend:
                friend = dict(friend)
                insert_query = chat_rooms.insert()
                chat_room_value = {
                    "deleted":0
                }
                await database.execute(insert_query, chat_room_value)
                select_query = "select * from chat_rooms order by id desc limit 1"
                chat_room_data = await database.fetch_one(select_query)
                chat_room_id = getattr(chat_room_data, "id")
                invite_insert_query = user_chat_rooms.insert()
                values1 = {
                    "user_id": user.id,
                    "chat_room_id": chat_room_id,
                    "valid": 0
                }
                values2 = {
                    "user_id": friend['id'],
                    "chat_room_id": chat_room_id,
                    "valid": 0
                }
                await database.execute(invite_insert_query, values1)
                await database.execute(invite_insert_query, values2)
    ret = await database.execute(query, values)
    return values

# usersを削除します。
@router.post("/users/delete")
async def users_delete(user: UserUpdate, database: Database = Depends(get_connection)):
    query = users.delete().where(users.columns.id==user.id)
    ret = await database.execute(query)
    return {"result": "delete success"}
