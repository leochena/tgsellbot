DEFAULT_LOCALE = "ru"

TRANSLATIONS: dict[str, dict[str, str]] = {
    "ru": {
        # === Common Buttons ===
        "btn.shop": "🏪 Магазин",
        "btn.rules": "📜 Правила",
        "btn.profile": "👤 Профиль",
        "btn.support": "🆘 Поддержка",
        "btn.channel": "ℹ Новостной канал",
        "btn.invite_group": "👥 Пригласить в группу",
        "btn.admin_menu": "🎛 Панель администратора",
        "btn.back": "⬅️ Назад",
        "btn.to_menu": "🏠 В меню",
        "btn.close": "✖ Закрыть",
        "btn.buy": "🛒 Купить",
        "btn.redeem_points": "🎯 Обменять за баллы",
        "btn.yes": "✅ Да",
        "btn.no": "❌ Нет",
        "btn.check": "🔄 Проверить",
        "btn.check_subscription": "🔄 Проверить подписку",
        "btn.pay": "💳 Оплатить",
        "btn.check_payment": "🔄 Проверить оплату",
        "btn.pay.crypto": "💎 CryptoPay",
        "btn.pay.stars": "⭐ Telegram Stars",
        "btn.pay.tg": "💸 Telegram Payments",
        "btn.checkin": "✅ Ежедневный чек-ин",
        "btn.lottery": "🎁 Розыгрыш",
        "common.yes": "Да",
        "common.no": "Нет",

        # === Admin Buttons (user management shortcuts) ===
        "btn.admin.view_profile": "👁 Посмотреть профиль",
        "btn.admin.promote": "⬆️ Назначить администратором",
        "btn.admin.demote": "⬇️ Снять администратора",
        "btn.admin.replenish_user": "💸 Пополнить баланс",
        "btn.admin.deduct_user": "💳 Списать с баланса",
        "btn.admin.block": "🚫 Заблокировать",
        "btn.admin.unblock": "✅ Разблокировать",

        # === Titles / Generic Texts ===
        "menu.title": "⛩️ Основное меню",
        "profile.caption": "👤 <b>Профиль</b> — <a href='tg://user?id={id}'>{name}</a>",
        "rules.not_set": "❌ Правила не были добавлены",
        "rules.balance_notice": (
            "📜 <b>Как пользоваться магазином</b>\n"
            "1. Пополните внутренний баланс <b>{balance_currency}</b> или используйте баллы за чек-ин.\n"
            "2. Откройте магазин, выберите категорию и товар. Если товара нет в наличии, покупка и корзина недоступны.\n"
            "3. Для покупки за баланс выберите количество, подтвердите заказ и получите цифровой файл/данные автоматически.\n"
            "4. Для обмена за баллы нажмите «Обменять за баллы». Лимит количества задаётся для каждого товара.\n"
            "5. Код пополнения баланса вводится в главном меню. Скидочный код товара вводится только на странице товара.\n"
            "6. В группе можно отмечаться ежедневно и приглашать друзей. Пригласительный бонус начисляется после чек-ина нового пользователя.\n"
            "7. Розыгрыши используют ваши билеты и/или призовой пул магазина; результаты публикуются ботом.\n\n"
            "Баланс <b>{balance_currency}</b> — внутренняя единица магазина, это не настоящий {pay_currency}. "
            "{stars_rate} "
            "Stars поступают на баланс Telegram Stars бота; вывод выполняется владельцем по правилам Telegram/Fragment."
        ),
        "rules.stars_rate_configured": "При оплате Telegram Stars счёт выставляется по курсу 1 {balance_currency} = {stars_per_value} ⭐.",
        "rules.stars_rate_unconfigured": "Если Telegram Stars включены, фактический курс отображается перед оплатой.",

        # === Subscription Flow ===
        "subscribe.prompt": "Для начала подпишитесь на новостной канал",
        "subscribe.open_channel": "Открыть канал",

        # === Profile ===
        "profile.referral_id": "👤 <b>Реферал</b> — <code>{id}</code>",
        "btn.replenish": "💳 Пополнить баланс",
        "btn.referral": "🎲 Реферальная система",
        "btn.purchased": "🎁 Купленные товары",

        # === Profile Info Lines ===
        "profile.id": "🆔 <b>ID</b> — <code>{id}</code>",
        "profile.balance": "💳 <b>Баланс</b> — <code>{amount}</code> {currency}",
        "profile.points": "🎯 <b>Баллы</b> — <code>{amount}</code>",
        "profile.total_topup": "💵 <b>Всего пополнено</b> — <code>{amount}</code> {currency}",
        "profile.purchased_count": "🎁 <b>Куплено товаров</b> — {count} шт",
        "profile.registration_date": "🕢 <b>Дата регистрации</b> — <code>{dt}</code>",

        # === Referral ===
        "referral.title": "💚 Реферальная система",
        "referral.link": "🔗 Ссылка: https://t.me/{bot_username}?start={user_id}",
        "referral.count": "Количество рефералов: {count}",
        "referral.description": (
            "📔 Реферальная система позволит Вам заработать деньги без всяких вложений. "
            "Необходимо всего лишь распространять свою реферальную ссылку и Вы будете получать "
            "{percent}% от суммы пополнений Ваших рефералов на Ваш баланс бота."
        ),
        "btn.view_referrals": "👥 Мои рефералы",
        "btn.view_earnings": "💰 Мои поступления",
        "btn.back_to_referral": "⬅️ К реферальной системе",

        "referrals.list.title": "👥 Ваши рефералы:",
        "referrals.list.empty": "У вас пока нет активных рефералов",
        "referrals.item.format": "ID: {telegram_id} | Принёс: {total_earned} {currency}",

        "referral.earnings.title": "💰 Поступления от реферала <code>{telegram_id}</code> (<a href='tg://user?id={telegram_id}'>{name}</a>):",
        "referral.earnings.empty": "От данного реферала <code>{id}</code> (<a href='tg://user?id={id}'>{name}</a>) пока не было поступлений",
        "referral.earning.format": "{amount} {currency} | {date} | (с {original_amount} {currency})",
        "referral.item.info": ("💰 Поступление номер: <code>{id}</code>\n"
                               "👤 Реферал: <code>{telegram_id}</code> (<a href='tg://user?id={telegram_id}'>{name}</a>)\n"
                               "🔢 Количество: {amount} {currency}\n"
                               "🕘 Дата: <code>{date}</code>\n"
                               "💵 С пополнения на {original_amount} {currency}"),

        "all.earnings.title": "💰 Все ваши реферальные поступления:",
        "all.earnings.empty": "У вас пока нет реферальных поступлений",
        "all.earning.format": "{amount} {currency} от ID:{referral_id} | {date}",

        "referrals.stats.template": (
            "📊 Статистика реферальной системы:\n\n"
            "👥 Активных рефералов: {active_count}\n"
            "💰 Всего заработано: {total_earned} {currency}\n"
            "📈 Общая сумма пополнений рефералов: {total_original} {currency}\n"
            "🔢 Количество начислений: {earnings_count}"
        ),

        # === Admin: Main Menu ===
        "admin.menu.main": "⛩️ Меню администратора",
        "admin.menu.shop": "🛒 Управление магазином",
        "admin.menu.goods": "📦 Управление позициями",
        "admin.menu.categories": "📂 Управление категориями",
        "admin.menu.users": "👥 Управление пользователями",
        "admin.menu.broadcast": "📣 Объявление в группу",
        "admin.menu.roles": "🛡 Управление ролями",
        "admin.menu.rights": "Недостаточно прав",

        # === Admin: Role Management ===
        "admin.roles.list_title": "🛡 Роли системы:",
        "admin.roles.create": "➕ Создать роль",
        "admin.roles.edit": "✏️ Редактировать",
        "admin.roles.delete": "🗑 Удалить",
        "admin.roles.detail": "🛡 <b>Роль</b>: {name}\n📋 Права: {perms}\n👥 Пользователей: {users}",
        "admin.roles.prompt_name": "Введите название роли (макс. 64 символа):",
        "admin.roles.name_invalid": "⚠️ Некорректное название (пустое или длиннее 64 символов).",
        "admin.roles.name_exists": "❌ Роль с таким именем уже существует",
        "admin.roles.select_perms": "Выберите права для роли «{name}»:",
        "admin.roles.confirm": "✅ Подтвердить",
        "admin.roles.created": "✅ Роль «{name}» создана",
        "admin.roles.updated": "✅ Роль «{name}» обновлена",
        "admin.roles.deleted": "✅ Роль удалена",
        "admin.roles.delete_confirm": "Вы уверены, что хотите удалить роль «{name}»?",
        "admin.roles.delete_fail": "❌ Не удалось удалить: {error}",
        "admin.roles.perm_denied": "⚠️ Недостаточно прав для этого действия",
        "admin.roles.assign_prompt": "Выберите роль для пользователя {id}:",
        "admin.roles.assigned": "✅ Роль {role} назначена пользователю {name}",
        "admin.roles.assigned_notify": "ℹ️ Вам назначена роль: {role}",
        "admin.roles.edit_name_prompt": "Введите новое название роли (или /skip чтобы оставить текущее):",
        "btn.admin.assign_role": "🛡 Назначить роль",

        # === Admin: User Management ===
        "admin.users.prompt_enter_id": "👤 Введите id пользователя,\nчтобы посмотреть | изменить его данные",
        "admin.users.invalid_id": "⚠️ Введите корректный числовой ID пользователя.",
        "admin.users.profile_unavailable": "❌ Профиль недоступен (такого пользователя никогда не существовало)",
        "admin.users.not_found": "❌ Пользователь не найден",
        "admin.users.cannot_change_owner": "Нельзя менять роль владельца",
        "admin.users.referrals": "👥 <b>Рефералы пользователя</b> — {count}",
        "admin.users.btn.view_referrals": "👥 Рефералы пользователя",
        "admin.users.btn.view_earnings": "💰 Поступления",
        "admin.users.role": "🎛 <b>Роль</b> — {role}",
        "admin.users.set_admin.success": "✅ Роль присвоена пользователю {name}",
        "admin.users.set_admin.notify": "✅ Вам присвоена роль АДМИНИСТРАТОРА бота",
        "admin.users.remove_admin.success": "✅ Роль отозвана у пользователя {name}",
        "admin.users.remove_admin.notify": "❌ У вас отозвана роль АДМИНИСТРАТОРА бота",
        "admin.users.balance.topped": "✅ Баланс пользователя {name} пополнен на {amount} {currency}",
        "admin.users.balance.topped.notify": "✅ Ваш баланс пополнен на {amount} {currency}",
        "admin.users.balance.deducted": "✅ С баланса пользователя {name} списано {amount} {currency}",
        "admin.users.balance.deducted.notify": "ℹ️ С вашего баланса списано {amount} {currency}",
        "admin.users.balance.insufficient": "❌ Недостаточно средств. Текущий баланс: {balance} {currency}",
        "admin.users.blocked.success": "🚫 Пользователь {name} заблокирован",
        "admin.users.unblocked.success": "✅ Пользователь {name} разблокирован",
        "admin.users.cannot_block_owner": "❌ Невозможно заблокировать владельца",
        "admin.users.status.blocked": "🚫 <b>Статус</b> — Заблокирован",

        # === Admin: Shop Management Menu ===
        "admin.shop.menu.title": "⛩️ Меню управления магазином",
        "admin.shop.menu.statistics": "📊 Статистика",
        "admin.shop.menu.logs": "📁 Показать логи",
        "admin.shop.menu.users": "👤 Пользователи",
        "admin.shop.menu.search_bought": "🔎 Поиск купленного товара",

        # === Admin: Categories Management ===
        "admin.categories.menu.title": "⛩️ Меню управления категориями",
        "admin.categories.add": "➕ Добавить категорию",
        "admin.categories.rename": "✏️ Переименовать категорию",
        "admin.categories.delete": "🗑 Удалить категорию",
        "admin.categories.prompt.add": "Введите название новой категории:",
        "admin.categories.prompt.delete": "Введите название категории для удаления:",
        "admin.categories.prompt.rename.old": "Введите текущее название категории, которую нужно переименовать:",
        "admin.categories.prompt.rename.new": "Введите новое имя для категории:",
        "admin.categories.add.exist": "❌ Категория не создана (такая уже существует)",
        "admin.categories.add.success": "✅ Категория создана",
        "admin.categories.delete.not_found": "❌ Категория не удалена (такой категории не существует)",
        "admin.categories.delete.success": "✅ Категория удалена",
        "admin.categories.rename.not_found": "❌ Категория не может быть обновлена (такой категории не существует)",
        "admin.categories.rename.exist": "❌ Переименование невозможно (категория с таким именем уже существует)",
        "admin.categories.rename.success": "✅ Категория \"{old}\" переименована в \"{new}\"",

        # === Admin: Goods / Items Management (Add / List / Item Info) ===
        "admin.goods.add_position": "➕ Добавить позицию",
        "admin.goods.add_item": "➕ Добавить товар в позицию",
        "admin.goods.update_position": "📝 Изменить позицию",
        "admin.goods.delete_position": "❌ Удалить позицию",
        "admin.goods.show_items": "📄 Показать товары в позиции",
        "admin.goods.add.prompt.name": "Введите название позиции",
        "admin.goods.add.name.exists": "❌ Позиция не может быть создана (такая позиция уже существует)",
        "admin.goods.add.prompt.description": "Введите описание для позиции:",
        "admin.goods.add.prompt.price": "Введите цену внутреннего баланса для позиции (число в {currency}):",
        "admin.goods.add.price.invalid": "⚠️ Некорректное значение цены. Введите число.",
        "admin.goods.add.prompt.category": "Введите категорию, к которой будет относиться позиция:",
        "admin.goods.add.category.not_found": "❌ Позиция не может быть создана (категория для привязки введена неверно)",
        "admin.goods.add.infinity.question": "У этой позиции будут бесконечные товары? (всем будет высылаться одна копия значения)",
        "admin.goods.add.values.prompt_multi": (
            "Введите товары для позиции по одному сообщению.\n"
            "Когда закончите ввод — нажмите «Добавить указанные товары»."
        ),
        "admin.goods.add.values.added": "✅ Товар «{value}» добавлен в список ({count} шт.)",
        "admin.goods.add.result.created": "✅ Позиция создана.",
        "admin.goods.add.result.added": "📦 Добавлено товаров: <b>{n}</b>",
        "admin.goods.add.result.skipped_db_dup": "↩️ Пропущено (уже были в БД): <b>{n}</b>",
        "admin.goods.add.result.skipped_batch_dup": "🔁 Пропущено (дубль в вводе): <b>{n}</b>",
        "admin.goods.add.result.skipped_invalid": "🚫 Пропущено (пустые/некорректные): <b>{n}</b>",
        "admin.goods.add.single.prompt_value": "Введите одно значение товара для позиции:",
        "admin.goods.add.single.empty": "⚠️ Значение не может быть пустым.",
        "admin.goods.add.single.created": "✅ Позиция создана, значение добавлено",
        "btn.add_values_finish": "Добавить указанные товары",
        "admin.goods.position.not_found": "❌ Товаров нет (Такой позиции не существует)",
        "admin.goods.list_in_position.empty": "ℹ️ В этой позиции пока нет товаров.",
        "admin.goods.list_in_position.title": "Товары в позиции:",
        "admin.goods.item.invalid": "Некорректные данные",
        "admin.goods.item.invalid_id": "Некорректный ID товара",
        "admin.goods.item.not_found": "Товар не найден",
        "admin.goods.prompt.enter_item_name": "Введите название позиции",
        "admin.goods.menu.title": "⛩️ Меню управления позициями",

        # === Admin: Goods / Items Update Flow ===
        "admin.goods.update.amount.prompt.name": "Введите название позиции",
        "admin.goods.update.amount.not_exists": "❌ Товар не может быть добавлен (такой позиции не существует)",
        "admin.goods.update.amount.infinity_forbidden": "❌ Товар не может быть добавлен (у данной позиции бесконечный товар)",
        "admin.goods.update.values.result.title": "✅ Товары добавлены",
        "admin.goods.update.position.invalid": "Позиция не найдена.",
        "admin.goods.update.position.exists": "Позиция с таким именем уже существует.",
        "admin.goods.update.prompt.name": "Введите название позиции",
        "admin.goods.update.not_exists": "❌ Позиция не может быть изменена (такой позиции не существует)",
        "admin.goods.update.prompt.new_name": "Введите новое имя для позиции:",
        "admin.goods.update.prompt.description": "Введите описание для позиции:",
        "admin.goods.update.infinity.make.question": "Вы хотите сделать товары бесконечными?",
        "admin.goods.update.infinity.deny.question": "Вы хотите отменить бесконечные товары?",
        "admin.goods.update.success": "✅ Позиция обновлена",

        # === Admin: Goods / Items Delete Flow ===
        "admin.goods.delete.prompt.name": "Введите название позиции",
        "admin.goods.delete.position.not_found": "❌ Позиция не удалена (Такой позиции не существует)",
        "admin.goods.delete.position.success": "✅ Позиция удалена",
        "admin.goods.item.delete.button": "❌ Удалить товар",
        "admin.goods.item.already_deleted_or_missing": "Товар уже удалён или не найден",
        "admin.goods.item.deleted": "✅ Товар удалён",

        # === Admin: Item Info ===
        "admin.goods.item.info.position": "<b>Позиция</b>: <code>{name}</code>",
        "admin.goods.item.info.price": "<b>Цена</b>: <code>{price}</code> {currency}",
        "admin.goods.item.info.id": "<b>Уникальный ID</b>: <code>{id}</code>",
        "admin.goods.item.info.value": "<b>Товар</b>: <code>{value}</code>",

        # === Admin: Logs ===
        "admin.shop.logs.caption": "Логи бота",
        "admin.shop.logs.empty": "❗️ Логов пока нет",

        # === Group Notifications ===
        "shop.group.new_upload": "Залив",
        "shop.group.item": "Товар",
        "shop.group.count": "Количество",

        # === Admin: Statistics ===
        "admin.shop.stats.template": (
            "Статистика магазина:\n"
            "➖➖➖➖➖➖➖➖➖➖➖➖➖\n"
            "<b>◽ПОЛЬЗОВАТЕЛИ</b>\n"
            "◾️Новых за 24 часа: {today_users}\n"
            "◾️Всего: {users}\n"
            "◾️Покупателей: {buyers}\n"
            "◾️Заблокировано: {blocked}\n"
            "➖➖➖➖➖➖➖➖➖➖➖➖➖\n"
            "◽<b>СРЕДСТВА</b>\n"
            "◾Продаж за 24 часа: {today_orders} {currency} ({today_sold_count} шт.)\n"
            "◾Продано всего на: {all_orders} {currency}\n"
            "◾Средний чек: {avg_order} {currency}\n"
            "◾Пополнений за 24 часа: {today_topups} {currency}\n"
            "◾Средств в системе: {system_balance} {currency}\n"
            "◾Пополнено всего: {all_topups} {currency}\n"
            "➖➖➖➖➖➖➖➖➖➖➖➖➖\n"
            "◽<b>КАТАЛОГ</b>\n"
            "◾В наличии: {items} шт.\n"
            "◾Позиций: {goods} шт.\n"
            "◾Категорий: {categories} шт.\n"
            "◾Продано: {sold_count} шт."
        ),
        "admin.shop.stats.roles_header": "\n➖➖➖➖➖➖➖➖➖➖➖➖➖\n◽<b>РОЛИ</b>",

        # === Admin: Lists & Broadcast ===
        "admin.shop.users.title": "Пользователи бота:",
        "admin.shop.bought.prompt_id": "Введите уникальный ID купленного товара",
        "admin.shop.bought.not_found": "❌ Товар с указанным уникальным ID не найден",
        "broadcast.prompt": "Отправьте текст объявления для группы/канала:",
        "broadcast.creating": "📤 Отправляем объявление...",
        "broadcast.progress": (
            "📤 Объявление отправляется...\n\n"
            "📊 Прогресс: {progress:.1f}%\n"
            "✅ Отправлено: {sent}/{total}\n"
            "❌ Ошибок: {failed}\n"
            "⏱ Прошло времени: {time} сек"),
        "broadcast.done": (
            "✅ Объявление отправлено.\n"
            "🎯 Получатель: {target}"
        ),
        "broadcast.cancel": "❌ Отправка объявления отменена",
        "broadcast.warning": "Нет активного объявления",
        "broadcast.target_missing": "❌ Не задана группа/канал для объявлений. Укажите ANNOUNCEMENT_CHAT_ID или CHANNEL_ID/CHANNEL_URL.",
        "broadcast.send_failed": "❌ Не удалось отправить объявление. Проверьте chat id и права бота в группе/канале.",
        "chatid.response": "chat_id: <code>{chat_id}</code>\ntype: <code>{chat_type}</code>",

        # === Payments / Top-up Flow ===
        "payments.replenish_prompt": "Введите сумму пополнения внутреннего баланса в {currency}:",
        "payments.replenish_invalid": "❌ Неверная сумма. Введите число от {min_amount} до {max_amount} {currency}.",
        "payments.deduct_prompt": "Введите сумму списания в {currency}:",
        "payments.deduct_invalid": "❌ Неверная сумма. Введите число от {min_amount} до {max_amount} {currency}.",
        "payments.method_choose": "Выберите способ оплаты:",
        "payments.not_configured": "❌ Пополнение не настроено",
        "payments.session_expired": "Сессия оплаты устарела. Начните заново.",
        "payments.crypto.create_fail": "❌ Ошибка при создании счёта: {error}",
        "payments.crypto.api_error": "❌ Ошибка CryptoPay API: {error}",
        "payments.crypto.check_fail": "❌ Ошибка проверки платежа: {error}",
        "payments.stars.create_fail": "❌ Не удалось выставить счёт в Stars: {error}",
        "payments.fiat.create_fail": "❌ Не удалось выставить счёт: {error}",
        "payments.no_active_invoice": "❌ Активных счетов не найдено. Начните пополнение заново.",
        "payments.invoice_not_found": "❌ Счёт не найден. Начните заново.",
        "payments.not_paid_yet": "⌛️ Платёж ещё не оплачен.",
        "payments.expired": "❌ Срок действия счёта истёк.",
        "payments.invoice.summary": (
            "💵 Сумма пополнения: {amount} {currency}.\n"
            "⌛️ У вас есть {minutes} минут на оплату.\n"
            "<b>❗️ После оплаты нажмите кнопку «{button}»</b>"
        ),
        "payments.unable_determine_amount": "❌ Не удалось определить сумму оплаты.",
        "payments.topped_simple": "✅ Баланс пополнен на {amount} {currency}",
        "payments.topped_with_suffix": "✅ Баланс пополнен на {amount} {currency} ({suffix})",
        "payments.success_suffix.stars": "Telegram Stars",
        "payments.success_suffix.tg": "Telegram Payments",
        "payments.referral.bonus": "✅ Вы получили {amount} {currency} от вашего реферала <a href='tg://user?id={id}'>{name}</a>",
        "payments.invoice.title.topup": "Пополнение баланса",
        "payments.invoice.desc.topup.stars": "Пополнение на {amount} {currency} через Telegram Stars",
        "payments.invoice.desc.topup.fiat": "Оплата через Telegram Payments (карта)",
        "payments.invoice.label.fiat": "Пополнение на {amount} {currency}",
        "payments.invoice.label.stars": "{stars} ⭐️",
        "payments.already_processed": "Этот платеж уже был обработан ✅",
        "payments.processing_error": "Ошибка при обработке платежа. Попробуйте позже.",

        # === Shop Browsing (Categories / Goods / Item Page) ===
        "shop.categories.title": "🏪 Категории магазина",
        "shop.goods.choose": "🏪 Выберите нужный товар",
        "shop.item.not_found": "Товар не найден",
        "shop.item.title": "🏪 Товар {name}",
        "shop.item.description": "Описание: {description}",
        "shop.item.price": "Цена внутреннего баланса — {amount} {currency}",
        "shop.item.points_price": "Цена в баллах — {points} баллов, максимум {max_count} за раз",
        "shop.item.quantity_unlimited": "Количество — неограниченно",
        "shop.item.quantity_left": "Количество — {count} шт.",
        "shop.insufficient_funds": "❌ Недостаточно средств",
        "shop.points.insufficient": "❌ Недостаточно баллов",
        "shop.points.not_available": "❌ Этот товар нельзя обменять за баллы",
        "shop.points.quantity_exceeded": "❌ Превышен лимит обмена за раз",
        "shop.points.choose_quantity": "Выберите количество для обмена. Максимум: {max}",
        "shop.purchase.choose_quantity": "Выберите количество для покупки. Максимум: {max}",
        "shop.out_of_stock": "❌ Товара нет в наличии",
        "shop.purchase.success": "✅ Товар куплен. <b>Баланс</b>: <i>{balance}</i> {currency}\n\n{value}",
        "shop.purchase.receipt": "✅ Заказ успешно оформлен!\n➖➖➖➖➖➖➖➖➖➖➖➖\n📃 Товар: {item_name}\n💰 Цена: {price} {currency}\n📦 Кол-во: {quantity} шт.\n💡 Заказ: {unique_id}\n🕐 Время: {datetime}\n💲 Итого: {total} {currency}\n👤 Покупатель: @{username} ({user_id})\n➖➖➖➖➖➖➖➖➖➖➖➖\n🔑 Значение:\n<code>{value}</code>",
        "shop.points.receipt": "✅ Товар обменян за баллы!\n➖➖➖➖➖➖➖➖➖➖➖➖\n📃 Товар: {item_name}\n🎯 Баллы: {points}\n📦 Кол-во: {quantity} шт.\n💡 Заказ: {unique_id}\n🕐 Время: {datetime}\n👤 Покупатель: @{username} ({user_id})\n🎯 Остаток баллов: {points_balance}\n➖➖➖➖➖➖➖➖➖➖➖➖\n🔑 Значение:\n<code>{value}</code>",
        "shop.purchase.processing": "⏳ Обрабатываем покупку...",
        "shop.purchase.fail.user_not_found": "❌ Пользователь не найден в системе",
        "shop.purchase.fail.general": "❌ Ошибка при покупке: {message}",

        # === Purchases ===
        "purchases.title": "Купленные товары:",
        "purchases.pagination.invalid": "Некорректные данные пагинации",
        "purchases.item.not_found": "Покупка не найдена",
        "purchases.item.name": "<b>🧾 Товар</b>: <code>{name}</code>",
        "purchases.item.price": "<b>💵 Цена</b>: <code>{amount}</code> {currency}",
        "purchases.item.datetime": "<b>🕒 Дата покупки</b>: <code>{dt}</code>",
        "purchases.item.unique_id": "<b>🧾 Уникальный ID</b>: <code>{uid}</code>",
        "purchases.item.value": "<b>🔑 Значение</b>:\n<code>{value}</code>",
        "purchases.item.buyer": "<b>Покупатель</b>: <code>{buyer}</code>",

        # === Middleware ===
        "middleware.ban": "⏳ Вы временно заблокированы. Подождите {time} секунд",
        "middleware.above_limits": "⚠️ Слишком много запросов! Вы временно заблокированы.",
        "middleware.waiting": "⏳ Подождите {time} секунд перед следующим действием.",
        "middleware.security.session_outdated": "⚠️ Сессия устарела. Пожалуйста, начните заново.",
        "middleware.security.invalid_data": "❌ Недопустимые данные",
        "middleware.security.blocked": "❌ Доступ заблокирован",
        "middleware.security.not_admin": "⛔ Недостаточно прав",
        "middleware.security.invalid_csrf": "⚠️ Сессия устарела. Пожалуйста, попробуйте снова.",
        "maintenance.active": "🔧 Бот находится на техническом обслуживании. Пожалуйста, попробуйте позже.",

        # === Admin: Maintenance ===
        "admin.menu.maintenance_on": "🔧 Тех. работы: ВКЛ",
        "admin.menu.maintenance_off": "🔧 Тех. работы: ВЫКЛ",
        "admin.maintenance.enabled": "✅ Режим тех. работ включён",
        "admin.maintenance.disabled": "✅ Режим тех. работ выключён",

        # === Promo Codes ===
        "btn.apply_promo": "🏷 Скидочный код товара",
        "btn.product_promo": "🏷 Скидочный код товара",
        "btn.remove_promo": "❌ Убрать скидочный код",
        "btn.remove_product_promo": "❌ Убрать скидочный код",
        "btn.balance_promo": "🏷 Код пополнения баланса",
        "admin.menu.promo": "🏷 Промокоды",
        "admin.promo.title": "🏷 <b>Управление промокодами</b>",
        "admin.promo.create": "➕ Создать промокод",
        "admin.promo.list_empty": "Промокодов пока нет.",
        "admin.promo.prompt.code": "Введите код промокода (до 50 символов):",
        "admin.promo.prompt.type": "Выберите тип скидки:",
        "admin.promo.type.percent": "📊 Процент (%)",
        "admin.promo.type.fixed": "💰 Фиксированная сумма",
        "admin.promo.prompt.value": "Введите размер скидки ({type}):",
        "admin.promo.prompt.max_uses": "Введите макс. число использований (0 = без лимита):",
        "admin.promo.prompt.expires": "Введите срок действия (ГГГГ-ММ-ДД) или 0 — бессрочно:",
        "admin.promo.prompt.binding": "Привязать к категории/товару?\n\nОтправьте:\n• Название категории\n• Название товара\n• 0 — без привязки",
        "admin.promo.created": "✅ Промокод <code>{code}</code> создан!",
        "admin.promo.code_exists": "❌ Промокод с таким кодом уже существует.",
        "admin.promo.deleted": "✅ Промокод удалён.",
        "admin.promo.toggled_on": "✅ Промокод активирован.",
        "admin.promo.toggled_off": "⛔ Промокод деактивирован.",
        "admin.promo.detail": "🏷 <b>Промокод</b>: <code>{code}</code>\n📊 Тип: {discount_type}\n💰 Скидка: {discount_value}\n🔢 Использований: {current_uses}/{max_uses}\n📅 Истекает: {expires_at}\n✅ Активен: {is_active}",
        "admin.promo.confirm_delete": "Удалить промокод <code>{code}</code>?",
        "admin.promo.invalid_value": "❌ Некорректное значение. Попробуйте ещё раз.",
        "admin.promo.invalid_date": "❌ Некорректная дата. Формат: ГГГГ-ММ-ДД",
        "promo.not_found": "❌ Промокод не найден.",
        "promo.inactive": "❌ Промокод неактивен.",
        "promo.expired": "❌ Промокод истёк.",
        "promo.max_uses_reached": "❌ Промокод исчерпан.",
        "promo.already_used": "❌ Вы уже использовали этот промокод.",
        "promo.wrong_item": "❌ Промокод не применим к этому товару.",
        "promo.wrong_category": "❌ Промокод не применим к этой категории.",
        "promo.applied": "✅ Промокод <code>{code}</code> применён! Скидка: {discount}",
        "promo.enter_code": "Введите скидочный код товара:",
        "promo.enter_product_code": "Введите скидочный код товара:",
        "promo.removed": "Промокод убран.",
        "promo.not_balance_type": "❌ Этот промокод не является промокодом на пополнение баланса.",
        "promo.enter_redeem_code": "Введите код пополнения баланса:",
        "promo.enter_balance_code": "Введите код пополнения баланса:",
        "promo.balance_redeemed": "✅ Промокод <code>{code}</code> активирован! На баланс начислено {amount} {currency}.",
        "shop.item.price_discounted": "💰 <b>Цена</b>: <s>{original}</s> <b>{discounted}</b> {currency} (промокод {code})",
        "admin.promo.type.balance": "💰 Пополнение баланса",
        "admin.promo.prompt.binding_type": "Привязать промокод к категории или товару?",
        "admin.promo.binding.category": "Категория",
        "admin.promo.binding.item": "Товар",
        "admin.promo.binding.none": "Без привязки",
        "admin.promo.prompt.category_name": "Введите название категории:",
        "admin.promo.prompt.item_name": "Введите название товара:",
        "admin.promo.category_not_found": "❌ Категория не найдена.",
        "admin.promo.item_not_found": "❌ Товар не найден.",
        "btn.redeem_promo": "🏷 Код пополнения баланса",
        "btn.language": "🌐 Язык",
        "language.select": "🌐 Выберите язык интерфейса",
        "language.updated": "✅ Язык обновлён",
        "language.unsupported": "❌ Этот язык не поддерживается",
        "language.name.ru": "Русский",
        "language.name.en": "English",
        "review.disabled": "Отзывы отключены.",

        # === Cart ===
        "btn.cart": "🛒 Корзина ({count})",
        "btn.cart_empty": "🛒 Корзина",
        "btn.add_to_cart": "🛒 В корзину",
        "btn.cart_checkout": "💳 Оформить заказ",
        "btn.cart_clear": "🗑 Очистить корзину",
        "cart.title": "🛒 <b>Корзина</b>",
        "cart.empty": "Корзина пуста.",
        "cart.item": "• {name} — {price} {currency}",
        "cart.total": "\n💰 <b>Итого</b>: {total} {currency}",
        "cart.added": "✅ {name} добавлен в корзину.",
        "cart.full": "❌ Корзина переполнена (макс. 10 товаров).",
        "cart.item_not_found": "❌ Товар не найден.",
        "cart.removed": "✅ Товар убран из корзины.",
        "cart.cleared": "✅ Корзина очищена.",
        "cart.checkout_confirm": "Оформить заказ на {count} товар(ов) за {total} {currency}?",
        "cart.checkout_success": "✅ Заказ оформлен! Куплено {count} товар(ов).\n\n💰 Остаток: {balance} {currency}",
        "cart.checkout_receipt": "✅ Заказ оформлен!\n➖➖➖➖➖➖➖➖➖➖➖➖\n📦 Кол-во: {count} шт.\n💲 Итого: {total} {currency}\n👤 Покупатель: @{username} ({user_id})\n🕐 Время: {datetime}\n➖➖➖➖➖➖➖➖➖➖➖➖\nНажмите на товар для просмотра:",
        "cart.checkout_fail": "❌ Не удалось оформить заказ: {reason}",
        "cart.items_unavailable": "Некоторые товары более недоступны и были убраны из корзины.",


        # === Operation History ===
        "btn.operation_history": "📋 История операций",
        "history.title": "📋 <b>История операций</b>",
        "history.empty": "История операций пуста.",
        "history.topup": "💰 Пополнение: +{amount} {currency}",
        "history.purchase": "🛒 Покупка: {amount} {currency}",
        "history.referral": "🎲 Реферальный бонус: +{amount} {currency}",
        "history.date": "📅 {date}",

        # === Check-in & Lottery ===
        "checkin.success": "✅ Чек-ин выполнен!\n🎯 Баллы: +{points}\n🎟 Билетов: +{tickets}\n🔥 Серия: {streak} дн.",
        "checkin.already": "✅ Сегодня вы уже отметились.\n🎟 Билетов сегодня: {tickets}\n🔥 Серия: {streak} дн.",
        "checkin.tomorrow_points": "📅 Завтра при чек-ине: +{points} балл(ов).",
        "group_invite.link": "👥 Скопируйте текст ниже и отправьте друзьям:\n<code>{share_text}</code>\n\nБонус приглашения начисляется после чек-ина нового пользователя. Награда: {reward}.",
        "group_invite.not_configured": "❌ Группа для приглашений не настроена.",
        "group_invite.create_failed": "❌ Не удалось создать ссылку. Проверьте, что бот является администратором группы и имеет право приглашать пользователей.",
        "group_invite.rewarded": "👥 Бонус приглашения начислен пригласившему: +{points} балл(ов).",
        "group_invite.reward.fixed": "+{points} балл(ов)",
        "group_invite.reward.range": "{start}-{end}: +{points}",
        "group_invite.reward.open": "{start}+: +{points}",
        "group_invite.welcome_usage": (
            "👋 Добро пожаловать, <b>{name}</b>!\n"
            "В этом чате можно использовать бота напрямую:\n"
            "✅ /checkin - ежедневный чек-ин и баллы\n"
            "👥 /invite - получить свою ссылку приглашения\n"
            "🎁 Баллы можно использовать для розыгрышей и обмена товаров."
        ),
        "lottery.no_active": "🎁 Активного розыгрыша сейчас нет.\n✅ Чек-ин сегодня: {checked}\n🔥 Серия: {streak} дн.",
        "lottery.active": "🎁 <b>{title}</b>\n🏆 Приз: {prize}\n🎟 Всего билетов: {entries}\n👥 Участников: {users}\n🎫 Ваши билеты: {my_entries}\n✅ Чек-ин сегодня: {checked}\n🔥 Серия: {streak} дн.",
        "admin.menu.lottery": "🎁 Розыгрыши",
        "admin.lottery.create": "➕ Создать розыгрыш",
        "admin.lottery.draw": "🎲 Определить победителя",
        "admin.lottery.close": "⛔ Закрыть без победителя",
        "admin.lottery.active": "🎁 <b>Активный розыгрыш #{id}</b>\nНазвание: {title}\nПриз: {prize}\n🎟 Билетов: {entries}\n👥 Участников: {users}",
        "admin.lottery.no_active": "🎁 Активного розыгрыша нет.",
        "admin.lottery.prompt_title": "Введите название розыгрыша:",
        "admin.lottery.prompt_prize": "Введите приз розыгрыша:",
        "admin.lottery.prompt_auto_draw": "Enter auto draw conditions, or 0 for manual draw. Example: time=2026-06-09T12:00:00+08:00; entries=100; users=20",
        "admin.lottery.auto_draw_invalid": "❌ Invalid auto draw config.",
        "admin.lottery.prize_pool": "Product prize pool",
        "admin.lottery.title_invalid": "❌ Название не может быть пустым.",
        "admin.lottery.prize_invalid": "❌ Приз не может быть пустым.",
        "admin.lottery.created": "✅ Розыгрыш #{id} создан: {title}",
        "admin.lottery.drawn": "🎉 Draw complete!\n🎁 {title}\n🏆 Prize pool: {prize}\n👥 Winners: {winners_count}\n👤 First winner: <code>{winner}</code>\n🎫 First winner tickets: {winner_tickets}\n🎟 Total tickets: {entries}\n👥 Participants: {users}",
        "admin.lottery.closed": "✅ Розыгрыш закрыт.",
        "admin.lottery.error.not_found": "❌ Розыгрыш не найден.",
        "admin.lottery.error.not_active": "❌ Розыгрыш уже не активен.",
        "admin.lottery.error.no_entries": "❌ Нет участников для розыгрыша.",
        "admin.lottery.error.no_prizes": "❌ No products in the prize pool.",
        "admin.lottery.error.not_enough_unique_users": "❌ Not enough unique users to assign prizes.",

        # === Reviews ===
        "btn.leave_review": "⭐ Оставить отзыв",
        "btn.view_reviews": "📝 Отзывы ({count})",
        "btn.skip_review_text": "⏭ Пропустить текст",
        "review.prompt_rating": "Оцените товар <b>{name}</b> от 1 до 5:",
        "review.prompt_text": "Напишите текст отзыва (до 500 символов) или нажмите «Пропустить»:",
        "review.created": "✅ Спасибо за отзыв!",
        "review.already_exists": "Вы уже оставили отзыв на этот товар.",
        "review.not_purchased": "Вы не покупали этот товар.",
        "review.avg_rating": "⭐ Рейтинг: {rating}/5 ({count} отзывов)",
        "review.item": "⭐ {rating}/5 — {text}",
        "review.item_no_text": "⭐ {rating}/5",
        "review.list_title": "📝 <b>Отзывы на {name}</b>",
        "review.list_empty": "Отзывов пока нет.",

        # === Errors ===
        "errors.not_subscribed": "Вы не подписались",
        "errors.something_wrong": "❌ Что-то пошло не так. Попробуйте ещё раз.",
        "errors.pagination_invalid": "Некорректные данные пагинации",
        "errors.invalid_data": "❌ Неправильные данные",
        "errors.id_should_be_number": "❌ ID должен быть числом.",
        "errors.channel.telegram_not_found": "Я не могу писать в канал. Добавьте меня админом канала для заливов @{channel} с правом публиковать сообщения.",
        "errors.channel.telegram_forbidden_error": "Канал не найден. Проверьте username канала для заливов @{channel}.",
        "errors.channel.telegram_bad_request": "Не удалось отправить в канал для заливов: {e}",
    },

    "en": {
        # === Common Buttons ===
        "btn.shop": "🏪 Shop",
        "btn.rules": "📜 Rules",
        "btn.profile": "👤 Profile",
        "btn.support": "🆘 Support",
        "btn.channel": "ℹ News channel",
        "btn.invite_group": "👥 Invite to group",
        "btn.admin_menu": "🎛 Admin panel",
        "btn.back": "⬅️ Back",
        "btn.to_menu": "🏠 Menu",
        "btn.close": "✖ Close",
        "btn.buy": "🛒 Buy",
        "btn.redeem_points": "🎯 Redeem with points",
        "btn.yes": "✅ Yes",
        "btn.no": "❌ No",
        "btn.check": "🔄 Check",
        "btn.check_subscription": "🔄 Check subscription",
        "btn.check_payment": "🔄 Check payment",
        "btn.pay": "💳 Pay",
        "btn.pay.crypto": "💎 CryptoPay",
        "btn.pay.stars": "⭐ Telegram Stars",
        "btn.pay.tg": "💸 Telegram Payments",
        "btn.checkin": "✅ Daily check-in",
        "btn.lottery": "🎁 Lottery",
        "common.yes": "Yes",
        "common.no": "No",

        # === Admin Buttons (user management shortcuts) ===
        "btn.admin.view_profile": "👁 View profile",
        "btn.admin.promote": "⬆️ Make admin",
        "btn.admin.demote": "⬇️ Remove admin",
        "btn.admin.replenish_user": "💸 Top up balance",
        "btn.admin.deduct_user": "💳 Deduct from balance",
        "btn.admin.block": "🚫 Block",
        "btn.admin.unblock": "✅ Unblock",

        # === Titles / Generic Texts ===
        "menu.title": "⛩️ Main menu",
        "profile.caption": "👤 <b>Profile</b> — <a href='tg://user?id={id}'>{name}</a>",
        "rules.not_set": "❌ Rules have not been added",
        "rules.balance_notice": (
            "📜 <b>How to trade in this shop</b>\n"
            "1. Top up the internal balance <b>{balance_currency}</b>, or use points earned from daily check-ins.\n"
            "2. Open the shop, choose a category and product. If stock is empty, purchase and cart actions are unavailable.\n"
            "3. For balance purchases, choose the quantity, confirm the order, and the digital file/data is delivered automatically.\n"
            "4. For point redemption, tap “Redeem with points”. Each product can have its own per-order quantity limit.\n"
            "5. Balance codes are redeemed from the main menu. Product discount codes are entered on the product page only.\n"
            "6. In the group, you can check in daily and invite friends. Invite rewards are credited after the new user checks in.\n"
            "7. Lotteries use your tickets and/or the shop prize pool; results are published by the bot.\n\n"
            "<b>{balance_currency}</b> is the shop's internal unit, not real {pay_currency}. "
            "{stars_rate} "
            "Stars are credited to the bot's Telegram Stars balance; withdrawal is handled by the owner under Telegram/Fragment rules."
        ),
        "rules.stars_rate_configured": "Telegram Stars top-ups are billed at 1 {balance_currency} = {stars_per_value} ⭐.",
        "rules.stars_rate_unconfigured": "If Telegram Stars are enabled, the actual rate is shown before payment.",

        # === Profile ===
        "btn.replenish": "💳 Top up your balance",
        "btn.referral": "🎲 Referral system",
        "btn.purchased": "🎁 Purchased goods",
        "profile.referral_id": "👤 <b>Referral</b> — <code>{id}</code>",

        # === Subscription Flow ===
        "subscribe.prompt": "First, subscribe to the news channel",
        "subscribe.open_channel": "Open channel",

        # === Profile Info Lines ===
        "profile.id": "🆔 <b>ID</b> — <code>{id}</code>",
        "profile.balance": "💳 <b>Balance</b> — <code>{amount}</code> {currency}",
        "profile.points": "🎯 <b>Points</b> — <code>{amount}</code>",
        "profile.total_topup": "💵 <b>Total topped up</b> — <code>{amount}</code> {currency}",
        "profile.purchased_count": "🎁 <b>Purchased items</b> — {count} pcs",
        "profile.registration_date": "🕢 <b>Registered at</b> — <code>{dt}</code>",

        # === Referral ===
        "referral.title": "💚 Referral system",
        "referral.link": "🔗 Link: https://t.me/{bot_username}?start={user_id}",
        "referral.count": "Referrals count: {count}",
        "referral.description": (
            "📔 The referral system lets you earn without any investment. "
            "Share your personal link and you will receive {percent}% of your referrals’ "
            "top-ups to your bot balance."
        ),
        "btn.view_referrals": "👥 My referrals",
        "btn.view_earnings": "💰 My earnings",
        "btn.back_to_referral": "⬅️ Back to referral system",

        "referrals.list.title": "👥 Your referrals:",
        "referrals.list.empty": "You don't have any active referrals yet",
        "referrals.item.format": "ID: {telegram_id} | Earned: {total_earned} {currency}",

        "referral.earnings.title": "💰 Earnings from referral <code>{telegram_id}</code> (<a href='tg://user?id={telegram_id}'>{name}</a>):",
        "referral.earnings.empty": "No earnings from this referral <code>{id}</code> (<a href='tg://user?id={id}'>{name}</a>) yet",
        "referral.earning.format": "{amount} {currency} | {date} | (from {original_amount} {currency})",
        "referral.item.info": ("💰 Earning number: <code>{id}</code>\n"
                               "👤 Referral: <code>{telegram_id}</code> (<a href='tg://user?id={telegram_id}'>{name}</a>)\n"
                               "🔢 Amount: {amount} {currency}\n"
                               "🕘 Date: <code>{date}</code>\n"
                               "💵 From a deposit to {original_amount} {currency}"),

        "all.earnings.title": "💰 All your referral earnings:",
        "all.earnings.empty": "You have no referral earnings yet",
        "all.earning.format": "{amount} {currency} from ID:{referral_id} | {date}",

        "referrals.stats.template": (
            "📊 Referral system statistics:\n\n"
            "👥 Active referrals: {active_count}\n"
            "💰 Total earned: {total_earned} {currency}\n"
            "📈 Total referrals top-ups: {total_original} {currency}\n"
            "🔢 Number of earnings: {earnings_count}"
        ),

        # === Admin: Main Menu ===
        "admin.menu.main": "⛩️ Admin Menu",
        "admin.menu.shop": "🛒 Shop management",
        "admin.menu.goods": "📦 Items management",
        "admin.menu.categories": "📂 Categories management",
        "admin.menu.users": "👥 Users management",
        "admin.menu.broadcast": "📣 Group announcement",
        "admin.menu.roles": "🛡 Role management",
        "admin.menu.rights": "Insufficient permissions",

        # === Admin: Role Management ===
        "admin.roles.list_title": "🛡 System roles:",
        "admin.roles.create": "➕ Create role",
        "admin.roles.edit": "✏️ Edit",
        "admin.roles.delete": "🗑 Delete",
        "admin.roles.detail": "🛡 <b>Role</b>: {name}\n📋 Permissions: {perms}\n👥 Users: {users}",
        "admin.roles.prompt_name": "Enter the role name (max 64 characters):",
        "admin.roles.name_invalid": "⚠️ Invalid name (empty or exceeds 64 characters).",
        "admin.roles.name_exists": "❌ A role with this name already exists",
        "admin.roles.select_perms": "Select permissions for role \"{name}\":",
        "admin.roles.confirm": "✅ Confirm",
        "admin.roles.created": "✅ Role \"{name}\" created",
        "admin.roles.updated": "✅ Role \"{name}\" updated",
        "admin.roles.deleted": "✅ Role deleted",
        "admin.roles.delete_confirm": "Are you sure you want to delete the role \"{name}\"?",
        "admin.roles.delete_fail": "❌ Failed to delete: {error}",
        "admin.roles.perm_denied": "⚠️ Insufficient permissions for this action",
        "admin.roles.assign_prompt": "Select a role for user {id}:",
        "admin.roles.assigned": "✅ Role {role} assigned to {name}",
        "admin.roles.assigned_notify": "ℹ️ Your role has been set to: {role}",
        "admin.roles.edit_name_prompt": "Enter the new role name (or /skip to keep current):",
        "btn.admin.assign_role": "🛡 Assign role",

        # === Admin: User Management ===
        "admin.users.prompt_enter_id": "👤 Enter the user ID to view / edit data",
        "admin.users.invalid_id": "⚠️ Please enter a valid numeric user ID.",
        "admin.users.profile_unavailable": "❌ Profile unavailable (such user never existed)",
        "admin.users.not_found": "❌ User not found",
        "admin.users.cannot_change_owner": "You cannot change the owner’s role",
        "admin.users.referrals": "👥 <b>User referrals</b> — {count}",
        "admin.users.btn.view_referrals": "👥 User's referrals",
        "admin.users.btn.view_earnings": "💰 User's earnings",
        "admin.users.role": "🎛 <b>Role</b> — {role}",
        "admin.users.set_admin.success": "✅ Role assigned to {name}",
        "admin.users.set_admin.notify": "✅ You have been granted the ADMIN role",
        "admin.users.remove_admin.success": "✅ Admin role revoked from {name}",
        "admin.users.remove_admin.notify": "❌ Your ADMIN role has been revoked",
        "admin.users.balance.topped": "✅ {name}'s balance has been topped up by {amount} {currency}",
        "admin.users.balance.topped.notify": "✅ Your balance has been topped up by {amount} {currency}",
        "admin.users.balance.deducted": "✅ Deducted {amount} {currency} from {name}'s balance",
        "admin.users.balance.deducted.notify": "ℹ️ {amount} {currency} has been deducted from your balance",
        "admin.users.balance.insufficient": "❌ Insufficient funds. Current balance: {balance} {currency}",
        "admin.users.blocked.success": "🚫 User {name} has been blocked",
        "admin.users.unblocked.success": "✅ User {name} has been unblocked",
        "admin.users.cannot_block_owner": "❌ Cannot block the owner",
        "admin.users.status.blocked": "🚫 <b>Status</b> — Blocked",

        # === Admin: Shop Management Menu ===
        "admin.shop.menu.title": "⛩️ Shop management",
        "admin.shop.menu.statistics": "📊 Statistics",
        "admin.shop.menu.logs": "📁 Show logs",
        "admin.shop.menu.users": "👤 Users",
        "admin.shop.menu.search_bought": "🔎 Search purchased item",

        # === Admin: Categories Management ===
        "admin.categories.menu.title": "⛩️ Categories management",
        "admin.categories.add": "➕ Add category",
        "admin.categories.rename": "✏️ Rename category",
        "admin.categories.delete": "🗑 Delete category",
        "admin.categories.prompt.add": "Enter a new category name:",
        "admin.categories.prompt.delete": "Enter the category name to delete:",
        "admin.categories.prompt.rename.old": "Enter the current category name to rename:",
        "admin.categories.prompt.rename.new": "Enter the new category name:",
        "admin.categories.add.exist": "❌ Category not created (already exists)",
        "admin.categories.add.success": "✅ Category created",
        "admin.categories.delete.not_found": "❌ Category not deleted (does not exist)",
        "admin.categories.delete.success": "✅ Category deleted",
        "admin.categories.rename.not_found": "❌ Category cannot be updated (does not exist)",
        "admin.categories.rename.exist": "❌ Cannot rename (a category with this name already exists)",
        "admin.categories.rename.success": "✅ Category \"{old}\" renamed to \"{new}\"",

        # === Admin: Goods / Items Management (Add / List / Item Info) ===
        "admin.goods.add_position": "➕ add item",
        "admin.goods.add_item": "➕ Add product to item",
        "admin.goods.update_position": "📝 change item",
        "admin.goods.delete_position": "❌ delete item",
        "admin.goods.show_items": "📄 show goods in item",
        "admin.goods.add.prompt.name": "Enter the item name",
        "admin.goods.add.name.exists": "❌ Item cannot be created (it already exists)",
        "admin.goods.add.prompt.description": "Enter item description:",
        "admin.goods.add.prompt.price": "Enter item internal balance price (number in {currency}):",
        "admin.goods.add.price.invalid": "⚠️ Invalid price. Please enter a number.",
        "admin.goods.add.prompt.category": "Enter the category the item belongs to:",
        "admin.goods.add.category.not_found": "❌ Item cannot be created (invalid category provided)",
        "admin.goods.add.infinity.question": "Should this item have infinite values? (everyone will receive the same value copy)",
        "admin.goods.add.values.prompt_multi": (
            "Send product values one per message.\n"
            "When finished, press “Add the listed goods”."
        ),
        "admin.goods.add.values.added": "✅ Value “{value}” added to the list ({count} pcs).",
        "admin.goods.add.result.created": "✅ Item has been created.",
        "admin.goods.add.result.added": "📦 Added values: <b>{n}</b>",
        "admin.goods.add.result.skipped_db_dup": "↩️ Skipped (already in DB): <b>{n}</b>",
        "admin.goods.add.result.skipped_batch_dup": "🔁 Skipped (duplicate in input): <b>{n}</b>",
        "admin.goods.add.result.skipped_invalid": "🚫 Skipped (empty/invalid): <b>{n}</b>",
        "admin.goods.add.single.prompt_value": "Enter a single value for the item:",
        "admin.goods.add.single.empty": "⚠️ Value cannot be empty.",
        "admin.goods.add.single.created": "✅ Item created, value added",
        "btn.add_values_finish": "Add the listed goods",
        "admin.goods.position.not_found": "❌ No goods (this item doesn't exist)",
        "admin.goods.list_in_position.empty": "ℹ️ There are no goods in this item yet.",
        "admin.goods.list_in_position.title": "Goods in item:",
        "admin.goods.item.invalid": "Invalid data",
        "admin.goods.item.invalid_id": "Invalid item ID",
        "admin.goods.item.not_found": "Item not found",
        "admin.goods.prompt.enter_item_name": "Enter the item name",
        "admin.goods.menu.title": "⛩️ Items management menu",

        # === Admin: Goods / Items Update Flow ===
        "admin.goods.update.amount.prompt.name": "Enter the item name",
        "admin.goods.update.amount.not_exists": "❌ Unable to add values (item does not exist)",
        "admin.goods.update.amount.infinity_forbidden": "❌ Unable to add values (this item is infinite)",
        "admin.goods.update.values.result.title": "✅ Values added",
        "admin.goods.update.position.invalid": "Item not found.",
        "admin.goods.update.position.exists": "An item with this name already exists.",
        "admin.goods.update.prompt.name": "Enter the item name",
        "admin.goods.update.not_exists": "❌ Item cannot be updated (does not exist)",
        "admin.goods.update.prompt.new_name": "Enter a new item name:",
        "admin.goods.update.prompt.description": "Enter item description:",
        "admin.goods.update.infinity.make.question": "Do you want to make the item infinite?",
        "admin.goods.update.infinity.deny.question": "Do you want to disable infinity?",
        "admin.goods.update.success": "✅ Item updated",

        # === Admin: Goods / Items Delete Flow ===
        "admin.goods.delete.prompt.name": "Enter the item name",
        "admin.goods.delete.position.not_found": "❌ item not deleted (this item doesn't exist)",
        "admin.goods.delete.position.success": "✅ item deleted",
        "admin.goods.item.delete.button": "❌ Delete item",
        "admin.goods.item.already_deleted_or_missing": "Item already deleted or not found",
        "admin.goods.item.deleted": "✅ Item deleted",

        # === Admin: Item Info ===
        "admin.goods.item.info.position": "<b>Item</b>: <code>{name}</code>",
        "admin.goods.item.info.price": "<b>Price</b>: <code>{price}</code> {currency}",
        "admin.goods.item.info.id": "<b>Unique ID</b>: <code>{id}</code>",
        "admin.goods.item.info.value": "<b>Product</b>: <code>{value}</code>",

        # === Admin: Logs ===
        "admin.shop.logs.caption": "Bot logs",
        "admin.shop.logs.empty": "❗️ No logs yet",

        # === Group Notifications ===
        "shop.group.new_upload": "New stock",
        "shop.group.item": "Item",
        "shop.group.count": "Quantity",

        # === Admin: Statistics ===
        "admin.shop.stats.template": (
            "Shop statistics:\n"
            "➖➖➖➖➖➖➖➖➖➖➖➖➖\n"
            "<b>◽USERS</b>\n"
            "◾️New in last 24h: {today_users}\n"
            "◾️Total: {users}\n"
            "◾️Buyers: {buyers}\n"
            "◾️Blocked: {blocked}\n"
            "➖➖➖➖➖➖➖➖➖➖➖➖➖\n"
            "◽<b>FUNDS</b>\n"
            "◾Sales in last 24h: {today_orders} {currency} ({today_sold_count} pcs)\n"
            "◾Total sold: {all_orders} {currency}\n"
            "◾Avg order: {avg_order} {currency}\n"
            "◾Top-ups in last 24h: {today_topups} {currency}\n"
            "◾Funds in system: {system_balance} {currency}\n"
            "◾Total top-ups: {all_topups} {currency}\n"
            "➖➖➖➖➖➖➖➖➖➖➖➖➖\n"
            "◽<b>CATALOG</b>\n"
            "◾In stock: {items} pcs\n"
            "◾Positions: {goods} pcs\n"
            "◾Categories: {categories} pcs\n"
            "◾Sold: {sold_count} pcs"
        ),
        "admin.shop.stats.roles_header": "\n➖➖➖➖➖➖➖➖➖➖➖➖➖\n◽<b>ROLES</b>",

        # === Admin: Lists & Broadcast ===
        "admin.shop.users.title": "Bot users:",
        "admin.shop.bought.prompt_id": "Enter purchased item unique ID",
        "admin.shop.bought.not_found": "❌ Item with given unique ID not found",
        "broadcast.prompt": "Send the group/channel announcement text:",
        "broadcast.creating": "📤 Sending announcement...",
        "broadcast.progress": (
            "📤 Announcement is being sent...\n\n\n"
            "📊 Progress: {progress:.1f}%{n}"
            "✅ Sent: {sent}/{total}\n"
            "❌ Errors: {failed}\n"
            "⏱ Time elapsed: {time} sec"),
        "broadcast.done": (
            "✅ Announcement sent.\n"
            "🎯 Target: {target}"
        ),
        "broadcast.cancel": "❌ Announcement sending has been canceled.",
        "broadcast.warning": "No active announcement",
        "broadcast.target_missing": "❌ Announcement group/channel is not configured. Set ANNOUNCEMENT_CHAT_ID or CHANNEL_ID/CHANNEL_URL.",
        "broadcast.send_failed": "❌ Failed to send the announcement. Check the chat id and bot permissions in the group/channel.",
        "chatid.response": "chat_id: <code>{chat_id}</code>\ntype: <code>{chat_type}</code>",

        # === Payments / Top-up Flow ===
        "payments.replenish_prompt": "Enter internal balance top-up amount in {currency}:",
        "payments.replenish_invalid": "❌ Invalid amount. Enter a number from {min_amount} to {max_amount} {currency}.",
        "payments.deduct_prompt": "Enter deduction amount in {currency}:",
        "payments.deduct_invalid": "❌ Invalid amount. Enter a number from {min_amount} to {max_amount} {currency}.",
        "payments.method_choose": "Choose a payment method:",
        "payments.not_configured": "❌ Top-ups are not configured",
        "payments.session_expired": "Payment session has expired. Please start again.",
        "payments.crypto.create_fail": "❌ Failed to create invoice: {error}",
        "payments.crypto.api_error": "❌ CryptoPay API error: {error}",
        "payments.crypto.check_fail": "❌ Payment check failed: {error}",
        "payments.stars.create_fail": "❌ Failed to issue Stars invoice: {error}",
        "payments.fiat.create_fail": "❌ Failed to issue invoice: {error}",
        "payments.no_active_invoice": "❌ No active invoices found. Start top-up again.",
        "payments.invoice_not_found": "❌ Invoice not found. Please start again.",
        "payments.not_paid_yet": "⌛️ Payment is not completed yet.",
        "payments.expired": "❌ Invoice has expired.",
        "payments.invoice.summary": (
            "💵 Top-up amount: {amount} {currency}.\n"
            "⌛️ You have {minutes} minutes to pay.\n"
            "<b>❗️ After paying, press «{button}»</b>"
        ),
        "payments.unable_determine_amount": "❌ Failed to determine the paid amount.",
        "payments.topped_simple": "✅ Balance topped up by {amount} {currency}",
        "payments.topped_with_suffix": "✅ Balance topped up by {amount} {currency} ({suffix})",
        "payments.success_suffix.stars": "Telegram Stars",
        "payments.success_suffix.tg": "Telegram Payments",
        "payments.referral.bonus": "✅ You received {amount} {currency} from your referral <a href='tg://user?id={id}'>{name}</a>",
        "payments.invoice.title.topup": "Balance top-up",
        "payments.invoice.desc.topup.stars": "Top-up {amount} {currency} via Telegram Stars",
        "payments.invoice.desc.topup.fiat": "Pay via Telegram Payments (card)",
        "payments.invoice.label.fiat": "Top-up {amount} {currency}",
        "payments.invoice.label.stars": "{stars} ⭐️",
        "payments.already_processed": "This payment has already been processed ✅",
        "payments.processing_error": "Payment processing error. Please try again later.",

        # === Shop Browsing (Categories / Goods / Item Page) ===
        "shop.categories.title": "🏪 Shop categories",
        "shop.goods.choose": "🏪 Choose a product",
        "shop.item.not_found": "Item not found",
        "shop.item.title": "🏪 Item {name}",
        "shop.item.description": "Description: {description}",
        "shop.item.price": "Internal balance price — {amount} {currency}",
        "shop.item.points_price": "Points price — {points} points, max {max_count} per redemption",
        "shop.item.quantity_unlimited": "Quantity — unlimited",
        "shop.item.quantity_left": "Quantity — {count} pcs",
        "shop.insufficient_funds": "❌ Insufficient funds",
        "shop.points.insufficient": "❌ Not enough points",
        "shop.points.not_available": "❌ This item cannot be redeemed with points",
        "shop.points.quantity_exceeded": "❌ Redemption quantity exceeds the per-order limit",
        "shop.points.choose_quantity": "Choose redemption quantity. Max: {max}",
        "shop.purchase.choose_quantity": "Choose purchase quantity. Max: {max}",
        "shop.out_of_stock": "❌ Item is out of stock",
        "shop.purchase.success": "✅ Item purchased. <b>Balance</b>: <i>{balance}</i> {currency}\n\n{value}",
        "shop.purchase.receipt": "✅ Order placed successfully!\n➖➖➖➖➖➖➖➖➖➖➖➖\n📃 Item: {item_name}\n💰 Price: {price} {currency}\n📦 Qty: {quantity}\n💡 Order: {unique_id}\n🕐 Time: {datetime}\n💲 Total: {total} {currency}\n👤 Buyer: @{username} ({user_id})\n➖➖➖➖➖➖➖➖➖➖➖➖\n🔑 Value:\n<code>{value}</code>",
        "shop.points.receipt": "✅ Item redeemed with points!\n➖➖➖➖➖➖➖➖➖➖➖➖\n📃 Item: {item_name}\n🎯 Points: {points}\n📦 Qty: {quantity}\n💡 Order: {unique_id}\n🕐 Time: {datetime}\n👤 Buyer: @{username} ({user_id})\n🎯 Points left: {points_balance}\n➖➖➖➖➖➖➖➖➖➖➖➖\n🔑 Value:\n<code>{value}</code>",
        "shop.purchase.processing": "⏳ Processing the purchase...",
        "shop.purchase.fail.user_not_found": "❌ User not found in the system",
        "shop.purchase.fail.general": "❌ Purchase error: {message}",

        # === Purchases ===
        "purchases.title": "Purchased items:",
        "purchases.pagination.invalid": "Invalid pagination data",
        "purchases.item.not_found": "Purchase not found",
        "purchases.item.name": "<b>🧾 Item</b>: <code>{name}</code>",
        "purchases.item.price": "<b>💵 Price</b>: <code>{amount}</code> {currency}",
        "purchases.item.datetime": "<b>🕒 Purchased at</b>: <code>{dt}</code>",
        "purchases.item.unique_id": "<b>🧾 Unique ID</b>: <code>{uid}</code>",
        "purchases.item.value": "<b>🔑 Value</b>:\n<code>{value}</code>",
        "purchases.item.buyer": "<b>Buyer</b>: <code>{buyer}</code>",

        # === Middleware ===
        "middleware.ban": "⏳ You are temporarily blocked. Wait {time} seconds.",
        "middleware.above_limits": "⚠️ Too many requests! You are temporarily blocked.",
        "middleware.waiting": "⏳ Wait {time} seconds for the next action.",
        "middleware.security.session_outdated": "⚠️ Session is outdated. Please start again.",
        "middleware.security.invalid_data": "❌ Invalid data",
        "middleware.security.blocked": "❌ Access blocked",
        "middleware.security.not_admin": "⛔ Insufficient permissions",
        "middleware.security.invalid_csrf": "⚠️ Session expired. Please try again.",
        "maintenance.active": "🔧 The bot is under maintenance. Please try again later.",

        # === Admin: Maintenance ===
        "admin.menu.maintenance_on": "🔧 Maintenance: ON",
        "admin.menu.maintenance_off": "🔧 Maintenance: OFF",
        "admin.maintenance.enabled": "✅ Maintenance mode enabled",
        "admin.maintenance.disabled": "✅ Maintenance mode disabled",

        # === Promo Codes ===
        "btn.apply_promo": "🏷 Product discount code",
        "btn.product_promo": "🏷 Product discount code",
        "btn.remove_promo": "❌ Remove discount code",
        "btn.remove_product_promo": "❌ Remove discount code",
        "btn.balance_promo": "🏷 Balance code",
        "admin.menu.promo": "🏷 Promo Codes",
        "admin.promo.title": "🏷 <b>Promo Code Management</b>",
        "admin.promo.create": "➕ Create promo code",
        "admin.promo.list_empty": "No promo codes yet.",
        "admin.promo.prompt.code": "Enter promo code (up to 50 characters):",
        "admin.promo.prompt.type": "Choose discount type:",
        "admin.promo.type.percent": "📊 Percent (%)",
        "admin.promo.type.fixed": "💰 Fixed amount",
        "admin.promo.prompt.value": "Enter discount value ({type}):",
        "admin.promo.prompt.max_uses": "Enter max uses (0 = unlimited):",
        "admin.promo.prompt.expires": "Enter expiry date (YYYY-MM-DD) or 0 for no expiry:",
        "admin.promo.prompt.binding": "Bind to category/item?\n\nSend:\n• Category name\n• Item name\n• 0 — no binding",
        "admin.promo.created": "✅ Promo code <code>{code}</code> created!",
        "admin.promo.code_exists": "❌ Promo code already exists.",
        "admin.promo.deleted": "✅ Promo code deleted.",
        "admin.promo.toggled_on": "✅ Promo code activated.",
        "admin.promo.toggled_off": "⛔ Promo code deactivated.",
        "admin.promo.detail": "🏷 <b>Promo Code</b>: <code>{code}</code>\n📊 Type: {discount_type}\n💰 Discount: {discount_value}\n🔢 Uses: {current_uses}/{max_uses}\n📅 Expires: {expires_at}\n✅ Active: {is_active}",
        "admin.promo.confirm_delete": "Delete promo code <code>{code}</code>?",
        "admin.promo.invalid_value": "❌ Invalid value. Try again.",
        "admin.promo.invalid_date": "❌ Invalid date. Format: YYYY-MM-DD",
        "promo.not_found": "❌ Promo code not found.",
        "promo.inactive": "❌ Promo code is inactive.",
        "promo.expired": "❌ Promo code has expired.",
        "promo.max_uses_reached": "❌ Promo code uses exhausted.",
        "promo.already_used": "❌ You already used this promo code.",
        "promo.wrong_item": "❌ Promo code is not applicable to this item.",
        "promo.wrong_category": "❌ Promo code is not applicable to this category.",
        "promo.applied": "✅ Promo code <code>{code}</code> applied! Discount: {discount}",
        "promo.enter_code": "Enter product discount code:",
        "promo.enter_product_code": "Enter product discount code:",
        "promo.removed": "Promo code removed.",
        "promo.not_balance_type": "❌ This promo code is not a balance top-up code.",
        "promo.enter_redeem_code": "Enter balance code:",
        "promo.enter_balance_code": "Enter balance code:",
        "promo.balance_redeemed": "✅ Promo code <code>{code}</code> redeemed! {amount} {currency} added to your balance.",
        "shop.item.price_discounted": "💰 <b>Price</b>: <s>{original}</s> <b>{discounted}</b> {currency} (promo {code})",
        "admin.promo.type.balance": "💰 Balance top-up",
        "admin.promo.prompt.binding_type": "Bind promo code to category or item?",
        "admin.promo.binding.category": "Category",
        "admin.promo.binding.item": "Item",
        "admin.promo.binding.none": "No binding",
        "admin.promo.prompt.category_name": "Enter category name:",
        "admin.promo.prompt.item_name": "Enter item name:",
        "admin.promo.category_not_found": "❌ Category not found.",
        "admin.promo.item_not_found": "❌ Item not found.",
        "btn.redeem_promo": "🏷 Balance code",
        "btn.language": "🌐 Language",
        "language.select": "🌐 Choose interface language",
        "language.updated": "✅ Language updated",
        "language.unsupported": "❌ This language is not supported",
        "language.name.ru": "Русский",
        "language.name.en": "English",
        "review.disabled": "Reviews are disabled.",

        # === Cart ===
        "btn.cart": "🛒 Cart ({count})",
        "btn.cart_empty": "🛒 Cart",
        "btn.add_to_cart": "🛒 Add to cart",
        "btn.cart_checkout": "💳 Checkout",
        "btn.cart_clear": "🗑 Clear cart",
        "cart.title": "🛒 <b>Cart</b>",
        "cart.empty": "Cart is empty.",
        "cart.item": "• {name} — {price} {currency}",
        "cart.total": "\n💰 <b>Total</b>: {total} {currency}",
        "cart.added": "✅ {name} added to cart.",
        "cart.full": "❌ Cart is full (max 10 items).",
        "cart.item_not_found": "❌ Item not found.",
        "cart.removed": "✅ Item removed from cart.",
        "cart.cleared": "✅ Cart cleared.",
        "cart.checkout_confirm": "Checkout {count} item(s) for {total} {currency}?",
        "cart.checkout_success": "✅ Order placed! Bought {count} item(s).\n\n💰 Balance: {balance} {currency}",
        "cart.checkout_receipt": "✅ Order placed!\n➖➖➖➖➖➖➖➖➖➖➖➖\n📦 Qty: {count}\n💲 Total: {total} {currency}\n👤 Buyer: @{username} ({user_id})\n🕐 Time: {datetime}\n➖➖➖➖➖➖➖➖➖➖➖➖\nTap an item to view details:",
        "cart.checkout_fail": "❌ Checkout failed: {reason}",
        "cart.items_unavailable": "Some items are no longer available and were removed from cart.",


        # === Operation History ===
        "btn.operation_history": "📋 Operation History",
        "history.title": "📋 <b>Operation History</b>",
        "history.empty": "Operation history is empty.",
        "history.topup": "💰 Top-up: +{amount} {currency}",
        "history.purchase": "🛒 Purchase: {amount} {currency}",
        "history.referral": "🎲 Referral bonus: +{amount} {currency}",
        "history.date": "📅 {date}",

        # === Check-in & Lottery ===
        "checkin.success": "✅ Check-in complete!\n🎯 Points: +{points}\n🎟 Tickets: +{tickets}\n🔥 Streak: {streak} day(s).",
        "checkin.already": "✅ You already checked in today.\n🎟 Tickets today: {tickets}\n🔥 Streak: {streak} day(s).",
        "checkin.tomorrow_points": "📅 Tomorrow's check-in reward: +{points} point(s).",
        "group_invite.link": "👥 Copy the text below and send it to friends:\n<code>{share_text}</code>\n\nInvite bonus is credited after the new user's check-in. Reward: {reward}.",
        "group_invite.not_configured": "❌ Invite group is not configured.",
        "group_invite.create_failed": "❌ Failed to create the invite link. Make sure the bot is a group admin with permission to invite users.",
        "group_invite.rewarded": "👥 Invite bonus credited to the inviter: +{points} point(s).",
        "group_invite.reward.fixed": "+{points} point(s)",
        "group_invite.reward.range": "{start}-{end}: +{points}",
        "group_invite.reward.open": "{start}+: +{points}",
        "group_invite.welcome_usage": (
            "👋 Welcome, <b>{name}</b>!\n"
            "You can use the bot directly in this group:\n"
            "✅ /checkin - daily check-in for points\n"
            "👥 /invite - get your invite link\n"
            "🎁 Points can be used for lottery entries and product redemption."
        ),
        "lottery.no_active": "🎁 There is no active lottery right now.\n✅ Checked in today: {checked}\n🔥 Streak: {streak} day(s).",
        "lottery.active": "🎁 <b>{title}</b>\n🏆 Prize: {prize}\n🎟 Total tickets: {entries}\n👥 Participants: {users}\n🎫 Your tickets: {my_entries}\n✅ Checked in today: {checked}\n🔥 Streak: {streak} day(s).",
        "admin.menu.lottery": "🎁 Lotteries",
        "admin.lottery.create": "➕ Create lottery",
        "admin.lottery.draw": "🎲 Draw winner",
        "admin.lottery.close": "⛔ Close without winner",
        "admin.lottery.active": "🎁 <b>Active lottery #{id}</b>\nTitle: {title}\nPrize: {prize}\n🎟 Tickets: {entries}\n👥 Participants: {users}",
        "admin.lottery.no_active": "🎁 No active lottery.",
        "admin.lottery.prompt_title": "Enter lottery title:",
        "admin.lottery.prompt_prize": "Enter lottery prize:",
        "admin.lottery.prompt_auto_draw": "Enter auto draw conditions, or 0 for manual draw. Example: time=2026-06-09T12:00:00+08:00; entries=100; users=20",
        "admin.lottery.auto_draw_invalid": "❌ Invalid auto draw config.",
        "admin.lottery.prize_pool": "Product prize pool",
        "admin.lottery.title_invalid": "❌ Title cannot be empty.",
        "admin.lottery.prize_invalid": "❌ Prize cannot be empty.",
        "admin.lottery.created": "✅ Lottery #{id} created: {title}",
        "admin.lottery.drawn": "🎉 Draw complete!\n🎁 {title}\n🏆 Prize pool: {prize}\n👥 Winners: {winners_count}\n👤 First winner: <code>{winner}</code>\n🎫 First winner tickets: {winner_tickets}\n🎟 Total tickets: {entries}\n👥 Participants: {users}",
        "admin.lottery.closed": "✅ Lottery closed.",
        "admin.lottery.error.not_found": "❌ Lottery not found.",
        "admin.lottery.error.not_active": "❌ Lottery is no longer active.",
        "admin.lottery.error.no_entries": "❌ No entries to draw.",
        "admin.lottery.error.no_prizes": "❌ No products in the prize pool.",
        "admin.lottery.error.not_enough_unique_users": "❌ Not enough unique users to assign prizes.",

        # === Reviews ===
        "btn.leave_review": "⭐ Leave a review",
        "btn.view_reviews": "📝 Reviews ({count})",
        "btn.skip_review_text": "⏭ Skip text",
        "review.prompt_rating": "Rate <b>{name}</b> from 1 to 5:",
        "review.prompt_text": "Write a review (up to 500 chars) or click Skip:",
        "review.created": "✅ Thank you for your review!",
        "review.already_exists": "You already reviewed this item.",
        "review.not_purchased": "You haven't purchased this item.",
        "review.avg_rating": "⭐ Rating: {rating}/5 ({count} reviews)",
        "review.item": "⭐ {rating}/5 — {text}",
        "review.item_no_text": "⭐ {rating}/5",
        "review.list_title": "📝 <b>Reviews for {name}</b>",
        "review.list_empty": "No reviews yet.",

        # === Errors ===
        "errors.not_subscribed": "You are not subscribed",
        "errors.something_wrong": "❌ Something went wrong. Please try again.",
        "errors.pagination_invalid": "Invalid pagination data",
        "errors.invalid_data": "❌ Invalid data",
        "errors.id_should_be_number": "❌ ID must be a number.",
        "errors.channel.telegram_not_found": "I can't write to the channel. Add me as a channel admin for uploads @{channel} with the right to publish messages.",
        "errors.channel.telegram_forbidden_error": "Channel not found. Check the channel username for uploads @{channel}.",
        "errors.channel.telegram_bad_request": "Failed to send to the channel for uploads: {e}",
        "errors.general_error": "❌ Error: {e}",
    },
}

ZH_OVERRIDES = {
    "btn.shop": "🏪 商店",
    "btn.rules": "📜 规则",
    "btn.profile": "👤 个人中心",
    "btn.support": "🆘 客服",
    "btn.channel": "ℹ 公告频道",
    "btn.invite_group": "👥 邀请加入群组",
    "btn.admin_menu": "🎛 管理后台",
    "btn.back": "⬅️ 返回",
    "btn.to_menu": "🏠 回到菜单",
    "btn.close": "✖ 关闭",
    "btn.buy": "🛒 购买",
    "btn.redeem_points": "🎯 积分兑换",
    "btn.yes": "✅ 是",
    "btn.no": "❌ 否",
    "btn.check": "🔄 检查",
    "btn.check_subscription": "🔄 检查订阅",
    "btn.pay": "💳 支付",
    "btn.check_payment": "🔄 检查支付",
    "btn.pay.crypto": "💎 CryptoPay",
    "btn.pay.stars": "⭐ Telegram Stars",
    "btn.pay.tg": "💸 Telegram Payments",
    "btn.checkin": "✅ 每日签到",
    "btn.lottery": "🎁 抽奖",
    "common.yes": "是",
    "common.no": "否",

    "menu.title": "⛩️ 主菜单",
    "profile.caption": "👤 <b>个人中心</b> — <a href='tg://user?id={id}'>{name}</a>",
    "rules.not_set": "❌ 暂未设置规则",
    "rules.balance_notice": (
        "📜 <b>交易规则与使用方法</b>\n"
        "1. 可以先充值内部余额 <b>{balance_currency}</b>，也可以通过每日签到获得积分。\n"
        "2. 进入商店后选择分类和商品。商品售罄时，购买和加入购物车按钮不会开放。\n"
        "3. 余额购买时先选择购买数量，确认后自动交付数字文件或内容。\n"
        "4. 积分兑换请点击“积分兑换”。每个商品可以单独设置单次兑换上限。\n"
        "5. 余额兑换码在机器人首页输入；商品折扣码只在商品详情页输入。\n"
        "6. 在群组中可以每日签到、生成邀请链接。新用户通过你的链接进群并签到后，你会获得邀请积分。\n"
        "7. 抽奖会使用你的抽奖券和/或商店奖品池，开奖结果由机器人公布。\n\n"
        "<b>{balance_currency}</b> 是本店内部记账单位，不是真实 {pay_currency}，不能提现为现金。"
        "{stars_rate}"
        "Stars 会进入机器人的 Telegram Stars 余额，提现需由机器人所有者按 Telegram/Fragment 规则处理。"
    ),
    "rules.stars_rate_configured": "使用 Telegram Stars 充值时，换算比例为 1 {balance_currency} = {stars_per_value} ⭐。",
    "rules.stars_rate_unconfigured": "如果启用 Telegram Stars，实际换算比例会在支付前显示。",
    "subscribe.prompt": "开始使用前，请先订阅公告频道",

    "profile.referral_id": "👤 <b>推荐人</b> — <code>{id}</code>",
    "btn.replenish": "💳 充值余额",
    "btn.referral": "🎲 推荐返利",
    "btn.purchased": "🎁 已购商品",
    "profile.id": "🆔 <b>ID</b> — <code>{id}</code>",
    "profile.balance": "💳 <b>余额</b> — <code>{amount}</code> {currency}",
    "profile.points": "🎯 <b>积分</b> — <code>{amount}</code>",
    "profile.total_topup": "💵 <b>累计充值</b> — <code>{amount}</code> {currency}",
    "profile.purchased_count": "🎁 <b>已购商品</b> — {count} 件",
    "profile.registration_date": "🕢 <b>注册时间</b> — <code>{dt}</code>",

    "referral.title": "💚 推荐返利",
    "referral.link": "🔗 推荐链接：https://t.me/{bot_username}?start={user_id}",
    "referral.count": "推荐人数：{count}",
    "referral.description": "分享你的推荐链接，用户通过链接进入并充值后，你将获得其充值金额 {percent}% 的返利。",
    "btn.view_referrals": "👥 我的推荐用户",
    "btn.view_earnings": "💰 我的返利",
    "btn.back_to_referral": "⬅️ 返回推荐返利",
    "referrals.list.title": "👥 你的推荐用户：",
    "referrals.list.empty": "你还没有活跃推荐用户",
        "referrals.item.format": "ID：{telegram_id} | 带来收益：{total_earned} {currency}",
    "referral.earnings.title": "💰 来自推荐用户 <code>{telegram_id}</code>（<a href='tg://user?id={telegram_id}'>{name}</a>）的返利：",
    "referral.earnings.empty": "推荐用户 <code>{id}</code>（<a href='tg://user?id={id}'>{name}</a>）暂无返利记录",
    "referral.earning.format": "{amount} {currency} | {date} | 原充值 {original_amount} {currency}",
    "referral.item.info": "💰 返利编号：<code>{id}</code>\n👤 推荐用户：<code>{telegram_id}</code>（<a href='tg://user?id={telegram_id}'>{name}</a>）\n🔢 金额：{amount} {currency}\n🕘 时间：<code>{date}</code>\n💵 来源充值：{original_amount} {currency}",
    "referrals.stats.template": "📊 推荐返利统计：\n\n👥 活跃推荐用户：{active_count}\n💰 累计返利：{total_earned} {currency}\n📈 推荐用户累计充值：{total_original} {currency}\n🔢 返利笔数：{earnings_count}",
        "all.earnings.title": "💰 你的全部推荐返利：",
        "all.earnings.empty": "你还没有推荐返利记录",
        "all.earning.format": "{amount} {currency} 来自 ID:{referral_id} | {date}",

    "admin.menu.main": "⛩️ 管理菜单",
    "admin.menu.shop": "🛒 商店管理",
    "admin.menu.goods": "📦 商品管理",
    "admin.menu.categories": "📂 分类管理",
    "admin.menu.users": "👥 用户管理",
    "admin.menu.broadcast": "📣 群组公告",
    "admin.menu.roles": "🛡 角色管理",
    "admin.menu.rights": "权限不足",
    "admin.menu.promo": "🏷 优惠码",
    "admin.menu.lottery": "🎁 抽奖管理",
    "admin.menu.maintenance_on": "🔧 维护模式：开启",
    "admin.menu.maintenance_off": "🔧 维护模式：关闭",
    "admin.maintenance.enabled": "✅ 已开启维护模式",
    "admin.maintenance.disabled": "✅ 已关闭维护模式",

    "admin.roles.list_title": "🛡 系统角色：",
    "admin.roles.create": "➕ 创建角色",
    "admin.roles.edit": "✏️ 编辑",
    "admin.roles.delete": "🗑 删除",
    "admin.roles.detail": "🛡 <b>角色</b>：{name}\n📋 权限：{perms}\n👥 用户数：{users}",
    "admin.roles.prompt_name": "请输入角色名称（最多 64 个字符）：",
    "admin.roles.name_invalid": "⚠️ 名称无效（不能为空，且不能超过 64 个字符）。",
    "admin.roles.name_exists": "❌ 该角色名称已存在",
    "admin.roles.select_perms": "请选择角色“{name}”的权限：",
    "admin.roles.confirm": "✅ 确认",
    "admin.roles.created": "✅ 角色“{name}”已创建",
    "admin.roles.updated": "✅ 角色“{name}”已更新",
    "admin.roles.deleted": "✅ 角色已删除",
    "admin.roles.delete_confirm": "确认删除角色“{name}”？",
    "admin.roles.delete_fail": "❌ 删除失败：{error}",
    "admin.roles.perm_denied": "⚠️ 权限不足，无法执行此操作",
    "admin.roles.assign_prompt": "请选择用户 {id} 的角色：",
    "admin.roles.assigned": "✅ 已将角色 {role} 分配给 {name}",
    "admin.roles.assigned_notify": "ℹ️ 你的角色已变更为：{role}",
    "admin.roles.edit_name_prompt": "请输入新的角色名称（或发送 /skip 保持不变）：",
    "btn.admin.assign_role": "🛡 分配角色",

    "admin.categories.menu.title": "⛩️ 分类管理",
    "admin.categories.add": "➕ 添加分类",
    "admin.categories.rename": "✏️ 重命名分类",
    "admin.categories.delete": "🗑 删除分类",
    "admin.categories.prompt.add": "请输入新分类名称：",
    "admin.categories.prompt.delete": "请输入要删除的分类名称：",
    "admin.categories.prompt.rename.old": "请输入要重命名的当前分类名称：",
    "admin.categories.prompt.rename.new": "请输入新的分类名称：",
    "admin.categories.add.exist": "❌ 分类未创建（已存在）",
    "admin.categories.add.success": "✅ 分类已创建",
    "admin.categories.delete.not_found": "❌ 分类未删除（不存在）",
    "admin.categories.delete.success": "✅ 分类已删除",
    "admin.categories.rename.not_found": "❌ 分类无法更新（不存在）",
    "admin.categories.rename.exist": "❌ 无法重命名（新名称已存在）",
    "admin.categories.rename.success": "✅ 分类“{old}”已重命名为“{new}”",

    "admin.goods.add_position": "➕ 添加商品位",
    "admin.goods.add_item": "➕ 给商品位补货",
    "admin.goods.update_position": "📝 修改商品位",
    "admin.goods.delete_position": "❌ 删除商品位",
    "admin.goods.show_items": "📄 查看商品位库存",
    "admin.goods.add.prompt.name": "请输入商品位名称：",
    "admin.goods.add.name.exists": "❌ 商品位未创建（已存在）",
    "admin.goods.add.prompt.description": "请输入商品位说明：",
    "admin.goods.add.prompt.price": "请输入商品位内部余额价格（单位 {currency}，数字）：",
    "admin.goods.add.price.invalid": "⚠️ 价格无效，请输入数字。",
    "admin.goods.add.prompt.category": "请输入该商品位所属分类：",
    "admin.goods.add.category.not_found": "❌ 商品位未创建（分类不存在）",
    "admin.goods.add.infinity.question": "这个商品位是否为无限库存？（所有买家都会收到同一个内容）",
    "admin.goods.add.values.prompt_multi": "请逐条发送要交付的库存内容。\n全部发送完后，点击“添加以上库存”。",
    "admin.goods.add.values.added": "✅ 已加入库存内容“{value}”（当前 {count} 条）。",
    "admin.goods.add.result.created": "✅ 商品位已创建。",
    "admin.goods.add.result.added": "📦 新增库存：<b>{n}</b>",
    "admin.goods.add.result.skipped_db_dup": "↩️ 已跳过（数据库已存在）：<b>{n}</b>",
    "admin.goods.add.result.skipped_batch_dup": "🔁 已跳过（本次重复）：<b>{n}</b>",
    "admin.goods.add.result.skipped_invalid": "🚫 已跳过（空值/无效）：<b>{n}</b>",
    "admin.goods.add.single.prompt_value": "请输入一个要交付的库存内容：",
    "admin.goods.add.single.empty": "⚠️ 库存内容不能为空。",
    "admin.goods.add.single.created": "✅ 商品位已创建，库存内容已添加",
    "btn.add_values_finish": "添加以上库存",
    "admin.goods.position.not_found": "❌ 没有库存（商品位不存在）",
    "admin.goods.list_in_position.empty": "ℹ️ 这个商品位暂无库存。",
    "admin.goods.list_in_position.title": "商品位库存：",
    "admin.goods.item.invalid": "数据无效",
    "admin.goods.item.invalid_id": "库存 ID 无效",
    "admin.goods.item.not_found": "库存不存在",
    "admin.goods.prompt.enter_item_name": "请输入商品位名称：",
    "admin.goods.menu.title": "⛩️ 商品管理",
    "admin.goods.update.amount.prompt.name": "请输入要补货的商品位名称：",
    "admin.goods.update.amount.not_exists": "❌ 无法补货（商品位不存在）",
    "admin.goods.update.amount.infinity_forbidden": "❌ 无法补货（该商品位是无限库存）",
    "admin.goods.update.values.result.title": "✅ 库存已添加",
    "admin.goods.update.position.invalid": "商品位不存在。",
    "admin.goods.update.position.exists": "该商品位名称已存在。",
    "admin.goods.update.prompt.name": "请输入要修改的商品位名称：",
    "admin.goods.update.not_exists": "❌ 商品位无法修改（不存在）",
    "admin.goods.update.prompt.new_name": "请输入新的商品位名称：",
    "admin.goods.update.prompt.description": "请输入商品位说明：",
    "admin.goods.update.infinity.make.question": "是否改为无限库存？",
    "admin.goods.update.infinity.deny.question": "是否取消无限库存？",
    "admin.goods.update.success": "✅ 商品位已更新",
    "admin.goods.delete.prompt.name": "请输入要删除的商品位名称：",
    "admin.goods.delete.position.not_found": "❌ 商品位未删除（不存在）",
    "admin.goods.delete.position.success": "✅ 商品位已删除",
    "admin.goods.item.delete.button": "❌ 删除库存",
    "admin.goods.item.already_deleted_or_missing": "库存已删除或不存在",
    "admin.goods.item.deleted": "✅ 库存已删除",
    "admin.goods.item.info.position": "<b>商品位</b>：<code>{name}</code>",
    "admin.goods.item.info.price": "<b>价格</b>：<code>{price}</code> {currency}",
    "admin.goods.item.info.id": "<b>库存 ID</b>：<code>{id}</code>",
    "admin.goods.item.info.value": "<b>交付内容</b>：<code>{value}</code>",

    "btn.admin.view_profile": "👁 查看资料",
    "btn.admin.promote": "⬆️ 设为管理员",
    "btn.admin.demote": "⬇️ 取消管理员",
    "btn.admin.replenish_user": "💸 给用户充值",
    "btn.admin.deduct_user": "💳 扣减余额",
    "btn.admin.block": "🚫 拉黑",
    "btn.admin.unblock": "✅ 解除拉黑",

    "admin.users.prompt_enter_id": "👤 请输入用户 ID，用于查看或修改资料",
    "admin.users.invalid_id": "⚠️ 请输入有效的数字用户 ID。",
    "admin.users.profile_unavailable": "❌ 资料不可用（该用户从未使用过机器人）",
    "admin.users.not_found": "❌ 用户不存在",
    "admin.users.cannot_change_owner": "不能修改所有者角色",
    "admin.users.referrals": "👥 <b>该用户推荐人数</b> — {count}",
    "admin.users.btn.view_referrals": "👥 该用户的推荐用户",
    "admin.users.btn.view_earnings": "💰 返利记录",
    "admin.users.role": "🎛 <b>角色</b> — {role}",
    "admin.users.set_admin.success": "✅ 已给 {name} 分配管理员角色",
    "admin.users.set_admin.notify": "✅ 你已获得机器人管理员角色",
    "admin.users.remove_admin.success": "✅ 已取消 {name} 的管理员角色",
    "admin.users.remove_admin.notify": "❌ 你的机器人管理员角色已被取消",
    "admin.users.balance.topped": "✅ 已给 {name} 充值 {amount} {currency}",
    "admin.users.balance.topped.notify": "✅ 你的余额已充值 {amount} {currency}",
    "admin.users.balance.deducted": "✅ 已从 {name} 余额扣除 {amount} {currency}",
    "admin.users.balance.deducted.notify": "ℹ️ 你的余额已扣除 {amount} {currency}",
    "admin.users.balance.insufficient": "❌ 余额不足。当前余额：{balance} {currency}",
    "admin.users.blocked.success": "🚫 已拉黑用户 {name}",
    "admin.users.unblocked.success": "✅ 已解除拉黑用户 {name}",
    "admin.users.cannot_block_owner": "❌ 不能拉黑所有者",
    "admin.users.status.blocked": "🚫 <b>状态</b> — 已拉黑",

    "admin.shop.menu.title": "⛩️ 商店管理",
    "admin.shop.menu.statistics": "📊 统计",
    "admin.shop.menu.logs": "📁 查看日志",
    "admin.shop.menu.users": "👤 用户列表",
    "admin.shop.menu.search_bought": "🔎 查询已购商品",
    "admin.shop.logs.caption": "机器人日志",
    "admin.shop.logs.empty": "❗️ 暂无日志",
    "admin.shop.stats.template": "商店统计：\n➖➖➖➖➖➖➖➖➖➖➖➖\n<b>◽用户</b>\n◾️近 24 小时新增：{today_users}\n◾️总用户：{users}\n◾️买家：{buyers}\n◾️已拉黑：{blocked}\n➖➖➖➖➖➖➖➖➖➖➖➖\n◽<b>资金</b>\n◾近 24 小时销售额：{today_orders} {currency}\n◾近 24 小时销量：{today_sold_count}\n◾累计销售额：{all_orders} {currency}\n◾平均订单：{avg_order} {currency}\n◾近 24 小时充值：{today_topups} {currency}\n◾用户余额总额：{system_balance} {currency}\n◾累计充值：{all_topups} {currency}\n➖➖➖➖➖➖➖➖➖➖➖➖\n◽<b>商品</b>\n◾库存条目：{items}\n◾商品位：{goods}\n◾分类：{categories}\n◾已售出：{sold_count}",
    "admin.shop.stats.roles_header": "\n➖➖➖➖➖➖➖➖➖➖➖➖\n◽<b>角色</b>",
    "admin.shop.users.title": "机器人用户：",
    "admin.shop.bought.prompt_id": "请输入已购商品订单号",
    "admin.shop.bought.not_found": "❌ 未找到该订单号对应的已购商品",

    "broadcast.prompt": "请输入要发送到群组/频道的公告内容：",
    "broadcast.creating": "📤 正在发送群组公告...",
    "broadcast.progress": "📤 群组公告发送中...\n\n📊 进度：{progress:.1f}%{n}✅ 已发送：{sent}/{total}\n❌ 失败：{failed}\n⏱ 已用时间：{time} 秒",
    "broadcast.done": "✅ 群组公告已发送。\n🎯 目标：{target}",
    "broadcast.cancel": "❌ 群组公告已取消",
    "broadcast.warning": "当前没有进行中的群组公告",
    "broadcast.target_missing": "❌ 还没有配置群组/频道公告目标。请设置 ANNOUNCEMENT_CHAT_ID，或设置 CHANNEL_ID/CHANNEL_URL。",
    "broadcast.send_failed": "❌ 群组公告发送失败。请检查群 ID，以及机器人在群组/频道里的发言权限。",
    "chatid.response": "chat_id: <code>{chat_id}</code>\ntype: <code>{chat_type}</code>",

    "payments.replenish_prompt": "请输入内部余额充值金额，单位 {currency}：",
    "payments.replenish_invalid": "❌ 金额无效。请输入 {min_amount} 到 {max_amount} {currency} 之间的数字。",
    "payments.deduct_prompt": "请输入扣减金额，单位 {currency}：",
    "payments.deduct_invalid": "❌ 金额无效。请输入 {min_amount} 到 {max_amount} {currency} 之间的数字。",
    "payments.method_choose": "请选择支付方式：",
    "payments.not_configured": "❌ 暂未配置充值方式",
    "payments.session_expired": "支付会话已过期，请重新开始。",
    "payments.crypto.create_fail": "❌ 创建 CryptoPay 账单失败：{error}",
    "payments.crypto.api_error": "❌ CryptoPay API 错误：{error}",
    "payments.crypto.check_fail": "❌ 检查支付失败：{error}",
    "payments.stars.create_fail": "❌ 创建 Stars 账单失败：{error}",
    "payments.fiat.create_fail": "❌ 创建支付账单失败：{error}",
    "payments.no_active_invoice": "❌ 没有可检查的支付订单，请重新发起充值。",
    "payments.invoice_not_found": "❌ 找不到支付订单，请重新发起充值。",
    "payments.not_paid_yet": "⌛️ 支付尚未完成。",
    "payments.expired": "❌ 账单已过期。",
    "payments.invoice.summary": "💵 充值金额：{amount} {currency}\n⌛️ 请在 {minutes} 分钟内完成支付。\n<b>❗️ 支付后请点击“{button}”</b>",
    "payments.unable_determine_amount": "❌ 无法确认到账金额。",
    "payments.topped_simple": "✅ 已充值 {amount} {currency}",
    "payments.topped_with_suffix": "✅ 已通过 {suffix} 充值 {amount} {currency}",
    "payments.success_suffix.stars": "Telegram Stars",
    "payments.success_suffix.tg": "Telegram Payments",
    "payments.invoice.title.topup": "余额充值",
    "payments.invoice.desc.topup.stars": "通过 Telegram Stars 充值 {amount} {currency}",
    "payments.invoice.desc.topup.fiat": "通过 Telegram Payments 支付",
    "payments.invoice.label.fiat": "充值 {amount} {currency}",
    "payments.invoice.label.stars": "{stars} ⭐️",
    "payments.already_processed": "这笔支付已经处理过 ✅",
    "payments.processing_error": "支付处理失败，请稍后重试。",
    "payments.referral.bonus": "✅ 你收到来自推荐用户 <a href='tg://user?id={id}'>{name}</a> 的返利：{amount} {currency}",

    "shop.categories.title": "🏪 商品分类",
    "shop.goods.choose": "🏪 请选择商品",
    "shop.item.not_found": "商品不存在",
    "shop.item.title": "🏪 商品 {name}",
    "shop.item.description": "说明：{description}",
    "shop.item.price": "余额价格 — {amount} {currency}",
    "shop.item.points_price": "积分价 — {points} 积分，单次最多 {max_count} 件",
    "shop.item.price_discounted": "💰 <b>价格</b>：<s>{original}</s> <b>{discounted}</b> {currency}（优惠码 {code}）",
    "shop.item.quantity_unlimited": "库存 — 无限",
    "shop.item.quantity_left": "库存 — {count} 件",
    "shop.insufficient_funds": "❌ 余额不足",
    "shop.points.insufficient": "❌ 积分不足",
    "shop.points.not_available": "❌ 该商品未开启积分兑换",
    "shop.points.quantity_exceeded": "❌ 超过该商品单次积分兑换上限",
    "shop.points.choose_quantity": "请选择积分兑换数量，单次最多 {max} 件：",
    "shop.purchase.choose_quantity": "请选择购买数量，单次最多 {max} 件：",
    "shop.out_of_stock": "❌ 商品已售罄",
    "shop.purchase.success": "✅ 购买成功。<b>余额</b>：<i>{balance}</i> {currency}\n\n{value}",
    "shop.purchase.processing": "⏳ 正在处理购买...",
    "shop.purchase.fail.user_not_found": "❌ 用户不存在",
    "shop.purchase.fail.general": "❌ 购买失败：{message}",
    "shop.purchase.receipt": "✅ 下单成功！\n➖➖➖➖➖➖➖➖➖➖➖➖\n📃 商品：{item_name}\n💰 单价：{price} {currency}\n📦 数量：{quantity}\n💡 订单号：{unique_id}\n🕐 时间：{datetime}\n💲 合计：{total} {currency}\n👤 买家：@{username} ({user_id})\n➖➖➖➖➖➖➖➖➖➖➖➖\n🔑 内容：\n<code>{value}</code>",
    "shop.points.receipt": "✅ 积分兑换成功！\n➖➖➖➖➖➖➖➖➖➖➖➖\n📃 商品：{item_name}\n🎯 消耗积分：{points}\n📦 数量：{quantity}\n💡 订单号：{unique_id}\n🕐 时间：{datetime}\n👤 买家：@{username} ({user_id})\n🎯 剩余积分：{points_balance}\n➖➖➖➖➖➖➖➖➖➖➖➖\n🔑 内容：\n<code>{value}</code>",
    "shop.group.new_upload": "新库存",
    "shop.group.item": "商品",
    "shop.group.count": "数量",

    "purchases.title": "已购商品：",
    "purchases.pagination.invalid": "分页数据无效",
    "purchases.item.not_found": "购买记录不存在",
    "purchases.item.name": "<b>🧾 商品</b>：<code>{name}</code>",
    "purchases.item.price": "<b>💵 价格</b>：<code>{amount}</code> {currency}",
    "purchases.item.datetime": "<b>🕒 购买时间</b>：<code>{dt}</code>",
    "purchases.item.unique_id": "<b>🧾 订单号</b>：<code>{uid}</code>",
    "purchases.item.value": "<b>🔑 内容</b>：\n<code>{value}</code>",
    "purchases.item.buyer": "<b>买家</b>：<code>{buyer}</code>",

    "btn.apply_promo": "🏷 商品折扣码",
    "btn.product_promo": "🏷 商品折扣码",
    "btn.remove_promo": "❌ 移除折扣码",
    "btn.remove_product_promo": "❌ 移除折扣码",
    "btn.redeem_promo": "🏷 余额兑换码",
    "btn.balance_promo": "🏷 余额兑换码",
    "promo.not_found": "❌ 优惠码不存在。",
    "promo.inactive": "❌ 优惠码未启用。",
    "promo.expired": "❌ 优惠码已过期。",
    "promo.max_uses_reached": "❌ 优惠码次数已用完。",
    "promo.already_used": "❌ 你已经使用过这个优惠码。",
    "promo.wrong_item": "❌ 这个优惠码不适用于该商品。",
    "promo.wrong_category": "❌ 这个优惠码不适用于该分类。",
    "promo.applied": "✅ 已使用优惠码 <code>{code}</code>，优惠：{discount}",
    "promo.enter_code": "请输入商品折扣码：",
    "promo.enter_product_code": "请输入商品折扣码：",
    "promo.removed": "已移除优惠码。",
    "promo.not_balance_type": "❌ 这个优惠码不是余额兑换码。",
    "promo.enter_redeem_code": "请输入余额兑换码：",
    "promo.enter_balance_code": "请输入余额兑换码：",
    "promo.balance_redeemed": "✅ 优惠码 <code>{code}</code> 兑换成功，已增加 {amount} {currency}。",

    "admin.promo.title": "🏷 <b>优惠码管理</b>",
    "admin.promo.create": "➕ 创建优惠码",
    "admin.promo.list_empty": "暂无优惠码。",
    "admin.promo.prompt.code": "请输入优惠码代码（最多 50 个字符）：",
    "admin.promo.prompt.type": "请选择优惠类型：",
    "admin.promo.type.percent": "📊 百分比（%）",
    "admin.promo.type.fixed": "💰 固定金额",
    "admin.promo.type.balance": "💰 余额兑换",
    "admin.promo.prompt.value": "请输入优惠数值（{type}）：",
    "admin.promo.prompt.max_uses": "请输入最大使用次数（0 = 不限）：",
    "admin.promo.prompt.expires": "请输入过期日期（YYYY-MM-DD），或 0 表示不过期：",
    "admin.promo.prompt.binding": "是否绑定分类/商品？\n\n发送：\n• 分类名称\n• 商品名称\n• 0 — 不绑定",
    "admin.promo.prompt.binding_type": "优惠码绑定到分类还是商品？",
    "admin.promo.binding.category": "分类",
    "admin.promo.binding.item": "商品",
    "admin.promo.binding.none": "不绑定",
    "admin.promo.prompt.category_name": "请输入分类名称：",
    "admin.promo.prompt.item_name": "请输入商品名称：",
    "admin.promo.created": "✅ 优惠码 <code>{code}</code> 已创建！",
    "admin.promo.code_exists": "❌ 该优惠码已存在。",
    "admin.promo.deleted": "✅ 优惠码已删除。",
    "admin.promo.toggled_on": "✅ 优惠码已启用。",
    "admin.promo.toggled_off": "⛔ 优惠码已停用。",
    "admin.promo.detail": "🏷 <b>优惠码</b>：<code>{code}</code>\n📊 类型：{discount_type}\n💰 优惠：{discount_value}\n🔢 使用次数：{current_uses}/{max_uses}\n📅 过期：{expires_at}\n✅ 启用：{is_active}",
    "admin.promo.confirm_delete": "确认删除优惠码 <code>{code}</code>？",
    "admin.promo.invalid_value": "❌ 数值无效，请重试。",
    "admin.promo.invalid_date": "❌ 日期无效。格式：YYYY-MM-DD",
    "admin.promo.category_not_found": "❌ 分类不存在。",
    "admin.promo.item_not_found": "❌ 商品不存在。",

    "btn.language": "🌐 语言",
    "language.select": "🌐 请选择界面语言",
    "language.updated": "✅ 语言已更新",
    "language.unsupported": "❌ 暂不支持该语言",
    "language.name.ru": "Русский",
    "language.name.en": "English",
    "language.name.zh": "中文",

    "btn.cart": "🛒 购物车（{count}）",
    "btn.cart_empty": "🛒 购物车",
    "btn.add_to_cart": "🛒 加入购物车",
    "btn.cart_checkout": "💳 结算",
    "btn.cart_clear": "🗑 清空购物车",
    "cart.title": "🛒 <b>购物车</b>",
    "cart.empty": "购物车为空。",
    "cart.item": "• {name} — {price} {currency}",
    "cart.total": "\n💰 <b>合计</b>：{total} {currency}",
    "cart.added": "✅ {name} 已加入购物车。",
    "cart.full": "❌ 购物车已满（最多 10 件）。",
    "cart.item_not_found": "❌ 商品不存在。",
    "cart.removed": "✅ 已移除商品。",
    "cart.cleared": "✅ 购物车已清空。",
    "cart.checkout_confirm": "确认结算 {count} 件商品，合计 {total} {currency}？",
    "cart.checkout_success": "✅ 下单成功！已购买 {count} 件商品。\n\n💰 余额：{balance} {currency}",
    "cart.checkout_receipt": "✅ 下单成功！\n➖➖➖➖➖➖➖➖➖➖➖➖\n📦 数量：{count}\n💲 合计：{total} {currency}\n👤 买家：@{username} ({user_id})\n🕐 时间：{datetime}\n➖➖➖➖➖➖➖➖➖➖➖➖\n点击商品查看详情：",
    "cart.checkout_fail": "❌ 结算失败：{reason}",
    "cart.items_unavailable": "部分商品已不可购买，已从购物车移除。",
    "cart.promo_expired": "购物车中的优惠码已失效，请重新选择优惠码。",

    "btn.operation_history": "📋 操作记录",
    "history.title": "📋 <b>操作记录</b>",
    "history.empty": "暂无操作记录。",
    "history.topup": "💰 充值：+{amount} {currency}",
    "history.purchase": "🛒 购买：{amount} {currency}",
    "history.referral": "🎲 推荐返利：+{amount} {currency}",
    "history.date": "📅 {date}",

    "checkin.success": "✅ 签到成功！\n🎯 积分：+{points}\n🎟 抽奖券：+{tickets}\n🔥 连续签到：{streak} 天。",
    "checkin.already": "✅ 今天已经签到过。\n🎟 今日抽奖券：{tickets}\n🔥 连续签到：{streak} 天。",
    "checkin.tomorrow_points": "📅 明天签到预计获得：+{points} 积分。",
    "group_invite.link": "👥 复制下面这段发给好友：\n<code>{share_text}</code>\n\n新用户通过链接进群并签到后，邀请奖励才会发放。奖励：{reward}。",
    "group_invite.not_configured": "❌ 还没有配置邀请群组。",
    "group_invite.create_failed": "❌ 创建邀请链接失败。请确认机器人是群管理员，并且有邀请用户/添加用户权限。",
    "group_invite.rewarded": "👥 已给邀请人发放邀请奖励：+{points} 积分。",
    "group_invite.reward.fixed": "+{points} 积分",
    "group_invite.reward.range": "第 {start}-{end} 人：+{points} 积分",
    "group_invite.reward.open": "第 {start} 人起：+{points} 积分",
    "group_invite.welcome_usage": (
        "👋 欢迎 <b>{name}</b> 加入！\n"
        "本群可以直接使用机器人：\n"
        "✅ /签到 - 每日签到领取积分\n"
        "👥 /邀请 - 生成你的专属邀请链接\n"
        "🎁 积分可参与抽奖，也可兑换商品。"
    ),
    "lottery.no_active": "🎁 当前没有进行中的抽奖。\n✅ 今日已签到：{checked}\n🔥 连续签到：{streak} 天。",
    "lottery.active": "🎁 <b>{title}</b>\n🏆 奖品：{prize}\n🎟 总抽奖券：{entries}\n👥 参与人数：{users}\n🎫 我的抽奖券：{my_entries}\n✅ 今日已签到：{checked}\n🔥 连续签到：{streak} 天。",
    "admin.lottery.create": "➕ 创建抽奖",
    "admin.lottery.draw": "🎲 开奖",
    "admin.lottery.close": "⛔ 不开奖并关闭",
    "admin.lottery.active": "🎁 <b>当前抽奖 #{id}</b>\n标题：{title}\n奖品：{prize}\n🎟 抽奖券：{entries}\n👥 参与人数：{users}",
    "admin.lottery.no_active": "🎁 当前没有进行中的抽奖。",
    "admin.lottery.prompt_title": "请输入抽奖标题：",
    "admin.lottery.prompt_prize": "请输入抽奖奖品：",
    "admin.lottery.prompt_auto_draw": "请输入自动开奖条件，发送 0 表示手动开奖。\n格式示例：\ntime=2026-06-09T12:00:00+08:00; entries=100; users=20\n任意一个条件满足就会自动开奖。",
    "admin.lottery.auto_draw_invalid": "❌ 自动开奖配置无效，请使用 time=ISO时间; entries=票数; users=人数，或发送 0。",
    "admin.lottery.prize_pool": "商品奖品池",
    "admin.lottery.title_invalid": "❌ 标题不能为空。",
    "admin.lottery.prize_invalid": "❌ 奖品不能为空。",
    "admin.lottery.created": "✅ 已创建抽奖 #{id}：{title}",
    "admin.lottery.drawn": "🎉 开奖完成！\n🎁 {title}\n🏆 奖品池：{prize}\n👥 中奖人数：{winners_count}\n👤 首位中奖用户：<code>{winner}</code>\n🎫 首位用户票数：{winner_tickets}\n🎟 总票数：{entries}\n👥 参与人数：{users}",
    "admin.lottery.closed": "✅ 抽奖已关闭。",
    "admin.lottery.error.not_found": "❌ 抽奖不存在。",
    "admin.lottery.error.not_active": "❌ 抽奖已不在进行中。",
    "admin.lottery.error.no_entries": "❌ 没有抽奖券，无法开奖。",
    "admin.lottery.error.no_prizes": "❌ 没有商品加入奖品池，无法开奖。",
    "admin.lottery.error.not_enough_unique_users": "❌ 参与用户不足，无法分配奖品。",

    "middleware.ban": "⏳ 你已被临时限制，请等待 {time} 秒。",
    "middleware.above_limits": "⚠️ 请求过于频繁，已被临时限制。",
    "middleware.waiting": "⏳ 请等待 {time} 秒后再操作。",
    "middleware.security.session_outdated": "⚠️ 会话已过期，请重新开始。",
    "middleware.security.invalid_data": "❌ 数据无效",
    "middleware.security.blocked": "❌ 访问已被限制",
    "middleware.security.not_admin": "⛔ 权限不足",
    "middleware.security.invalid_csrf": "⚠️ 会话已过期，请重试。",
    "maintenance.active": "🔧 机器人维护中，请稍后再试。",

    "btn.leave_review": "⭐ 评价",
    "btn.view_reviews": "📝 评价（{count}）",
    "btn.skip_review_text": "⏭ 跳过文字",
    "review.disabled": "评价功能已关闭。",
    "review.prompt_rating": "请给 <b>{name}</b> 评分，1 到 5 分：",
    "review.prompt_text": "请填写评价内容（最多 500 字），也可以点击跳过：",
    "review.created": "✅ 感谢你的评价！",
    "review.already_exists": "你已经评价过这个商品。",
    "review.not_purchased": "你还没有购买过这个商品。",
    "review.avg_rating": "⭐ 评分：{rating}/5（{count} 条评价）",
    "review.item": "⭐ {rating}/5 — {text}",
    "review.item_no_text": "⭐ {rating}/5",
    "review.list_title": "📝 <b>{name} 的评价</b>",
    "review.list_empty": "暂无评价。",

    "errors.not_subscribed": "你还没有订阅",
    "errors.something_wrong": "❌ 出错了，请稍后重试。",
    "errors.pagination_invalid": "分页数据无效",
    "errors.invalid_data": "❌ 数据无效",
    "errors.id_should_be_number": "❌ ID 必须是数字。",
    "errors.channel.telegram_not_found": "我无法向上传频道 @{channel} 发消息，请把机器人加入频道并授予发消息权限。",
    "errors.channel.telegram_forbidden_error": "找不到上传频道 @{channel}，请检查频道用户名。",
    "errors.channel.telegram_bad_request": "发送到上传频道失败：{e}",
    "errors.general_error": "❌ 错误：{e}",
}

TRANSLATIONS["zh"] = {**TRANSLATIONS["en"], **ZH_OVERRIDES}
for _locale_strings in TRANSLATIONS.values():
    _locale_strings.setdefault("language.name.zh", "中文")
