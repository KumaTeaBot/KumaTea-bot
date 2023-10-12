import os
import re
import json
import bot_db
import asyncio
from random import choice
from pyrogram import Client
from tools_tg import is_admin
from pyrogram.enums.parse_mode import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery


def read_poll_groups():
    if os.path.isfile(bot_db.poll_groups_file):
        with open(bot_db.poll_groups_file, 'r', encoding='utf-8') as file:
            for line in file:
                bot_db.poll_groups.append(int(line.strip()))
    return bot_db.poll_groups


def write_poll_groups(groups: list):
    with open(bot_db.poll_groups_file, 'w', encoding='utf-8') as file:
        file.write('\n'.join([str(group) for group in groups]))


def add_poll_group(group_id: int):
    # if group_id not in bot_db.poll_groups:
    bot_db.poll_groups.append(group_id)
    write_poll_groups(bot_db.poll_groups)


def del_poll_group(group_id: int):
    # if group_id in bot_db.poll_groups:
    bot_db.poll_groups.remove(group_id)
    write_poll_groups(bot_db.poll_groups)


async def enable_group(client: Client, message: Message):
    chat_id = message.chat.id
    if chat_id in bot_db.poll_groups:
        return await message.reply_text('本群已经启用抽奖了', quote=False)
    else:
        if await is_admin(chat_id, message.from_user.id, client):
            add_poll_group(chat_id)
            return await message.reply_text('本群成功启用抽奖！', quote=False)
        else:
            return await message.reply_text('仅管理员可操作', quote=False)


async def disable_group(client: Client, message: Message):
    chat_id = message.chat.id
    if chat_id in bot_db.poll_groups:
        if await is_admin(chat_id, message.from_user.id, client):
            del_poll_group(chat_id)
            return await message.reply_text('本群成功禁用抽奖！', quote=False)
        else:
            return await message.reply_text('仅管理员可操作', quote=False)
    else:
        return await message.reply_text('本群没有启用抽奖', quote=False)


async def kw_reply(message: Message):
    chat_id = message.chat.id
    if chat_id not in bot_db.poll_groups:
        return None

    text = message.text or message.caption
    include_list = bot_db.kw_reply_dict

    text_to_reply = ''
    match_item = ''
    for item in include_list:
        keywords = include_list[item]['keywords']
        for keyword in keywords:
            if keyword in text.lower():
                if include_list[item]['reply']:
                    text_to_reply = include_list[item]['reply']
                else:
                    text_to_reply = text
                match_item = item
                break
        if text_to_reply:
            if 'skip' in include_list[match_item]:
                keywords = include_list[match_item]['skip']
                for keyword in keywords:
                    if keyword in text.lower():
                        # text_to_reply = ''
                        # break
                        return None
    if text_to_reply:
        if 'RANDUSER' in text_to_reply:
            text_to_reply = text_to_reply.replace('RANDUSER', choice(bot_db.poll_candidates.values()))
        return await message.reply_text(text_to_reply, quote=include_list[match_item]['quote'])
    return None


async def replace_brackets(message: Message):
    # pool_candidates = {
    #    id: 'name',
    # }
    candidates = list(bot_db.poll_candidates.values())
    text = message.text or message.caption
    result = re.findall(bot_db.brackets_re, text)
    if len(result) == 0:
        return None
    elif len(result) == 1 and text.endswith(result[0]):
        return None
    else:
        for i in result:
            text = text.replace(i, choice(candidates), 1)
        return await message.reply_text(text, quote=False)


def read_candidates():
    if os.path.isfile(bot_db.poll_candidates_file):
        with open(bot_db.poll_candidates_file, 'r', encoding='utf-8') as file:
            bot_db.poll_candidates = json.load(file)
    return bot_db.poll_candidates


def write_candidates():
    with open(bot_db.poll_candidates_file, 'w', encoding='utf-8') as file:
        json.dump(bot_db.poll_candidates, file)


def add_candidate(user_id: int, name: str):
    bot_db.poll_candidates[user_id] = name
    write_candidates()


def del_candidate(user_id: int):
    bot_db.poll_candidates.pop(user_id)
    write_candidates()


async def apply_delete_from_candidates(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in bot_db.poll_candidates:
        inform_text = (f'您的昵称：{bot_db.poll_candidates[user_id]}\n'
                       f'是否确认删除？')
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton('确认', callback_data=f'poll_del_{user_id}_y')],
            [InlineKeyboardButton('取消', callback_data=f'poll_del_{user_id}_n')]
        ])
        return await message.reply_text(chat_id, inform_text, reply_markup=reply_markup, quote=False)


async def callback_delete(client: Client, callback_query: CallbackQuery):
    task, subtask, user_id, confirm = callback_query.data.split('_')
    message = callback_query.message
    async_tasks = []
    if callback_query.from_user.id == int(user_id):
        if confirm == 'y':
            del_candidate(user_id)
            async_tasks.append(message.edit_text('删除成功！'))
            async_tasks.append(callback_query.answer('删除成功！'))
        else:
            async_tasks.append(message.edit_text('已取消删除'))
            async_tasks.append(callback_query.answer('已取消删除'))
    else:
        async_tasks.append(callback_query.answer('不是你的别乱按！', show_alert=True))
    return await asyncio.gather(*async_tasks)


async def apply_add_to_candidates(client: Client, message: Message):
    user_id = message.from_user.id
    command = message.text
    content_index = command.find(' ')

    if content_index == -1:
        return await message.reply(
            '请在命令后面加上昵称\n'
            '`/help poll`',
            parse_mode=ParseMode.MARKDOWN,
            quote=False
        )

    name = command[content_index + 1:].strip()
    if len(name) > 2:
        return await message.reply(
            '昵称不可超过两个字\n'
            '`/help poll`',
            parse_mode=ParseMode.MARKDOWN,
            quote=False
        )
    if not (name.endswith('比') or name.endswith('批') or name[-1] == name[-2]):
        return await message.reply(
            '昵称必须以「比」「批」结尾或为叠词\n'
            '`/help poll`',
            parse_mode=ParseMode.MARKDOWN,
            quote=False
        )

    if user_id in bot_db.poll_candidates:
        return await message.reply(
            f'您已经有昵称 {bot_db.poll_candidates[user_id]} 了\n'
            f'如需更改请先删除\n'
            f'`/help poll`',
            parse_mode=ParseMode.MARKDOWN,
            quote=False
        )

    inform_text = (f'您的昵称：{name}\n'
                   f'正在等待管理员确认……')
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton('确认 (管)', callback_data=f'poll_add_{user_id}_y')],
        [InlineKeyboardButton('取消 (自)', callback_data=f'poll_add_{user_id}_n')]
    ])
    return await message.reply_text(inform_text, reply_markup=reply_markup, quote=False)


async def callback_add(client: Client, callback_query: CallbackQuery):
    task, subtask, user_id, confirm = callback_query.data.split('_')
    message = callback_query.message
    name = message.text.split('：')[1].split('\n')[0]
    async_tasks = []
    if callback_query.from_user.id == int(user_id) and confirm == 'n':
        async_tasks.append(message.edit_text('已取消添加'))
        async_tasks.append(callback_query.answer('已取消添加'))
    elif callback_query.from_user.id in bot_db.poll_admins and confirm == 'y':
        add_candidate(user_id, name)
        async_tasks.append(message.edit_text(f'您的昵称：{name}\n添加成功！'))
        async_tasks.append(callback_query.answer('添加成功！'))
    else:
        async_tasks.append(callback_query.answer('不是你的别乱按！', show_alert=True))
    return await asyncio.gather(*async_tasks)


async def poll_callback_handler(client, callback_query):
    subtask = callback_query.data.split('_')[1]

    if subtask == 'add':
        return await callback_add(client, callback_query)
    elif subtask == 'del':
        return await callback_delete(client, callback_query)
    return None
