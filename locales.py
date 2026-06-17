"""
locales.py — Complete bilingual (English / Amharic) string dictionary.
Usage:  from locales import get_text
        text = get_text('welcome', lang='am')
"""

STRINGS: dict[str, dict[str, str]] = {
    # ── Registration ────────────────────────────────────────────────────────
    "ask_phone": {
        "en": "📱 Welcome! Please share your phone number to continue (format: 09XXXXXXXX):",
        "am": "📱 እንኳን ደህና መጡ! አቤቱታ ስልክ ቁጥሮን ያጋሩ (ቅርጸት: 09XXXXXXXX):",
    },
    "invalid_phone": {
        "en": "❌ Invalid phone number. Please enter a valid Ethiopian number (09XXXXXXXX):",
        "am": "❌ ስልክ ቁጥሩ ትክክል አይደለም። ትክክለኛ ቁጥር ያስገቡ (09XXXXXXXX):",
    },
    "phone_saved": {
        "en": "✅ Phone number saved! Welcome to Habesha Bet Bingo 🎉",
        "am": "✅ ስልክ ቁጥሩ ተቀምጧል! ወደ ሃበሻ ቤት ቢንጎ እንኳን ደህና መጡ 🎉",
    },

    # ── Main menu ────────────────────────────────────────────────────────────
    "main_menu": {
        "en": "🏠 <b>Main Menu</b>\nBalance: <b>{balance} ETB</b>",
        "am": "🏠 <b>ዋና ምናሌ</b>\nቀሪ ሂሳብ: <b>{balance} ብር</b>",
    },
    "btn_play":        {"en": "🎮 Play Games",   "am": "🎮 ጨዋታ ተጫወት"},
    "btn_deposit":     {"en": "💰 Deposit",       "am": "💰 ተቀማጭ"},
    "btn_withdraw":    {"en": "💸 Withdraw",      "am": "💸 ማውጣት"},
    "btn_transfer":    {"en": "💱 Transfer",      "am": "💱 ማስተላለፍ"},
    "btn_profile":     {"en": "👤 My Profile",    "am": "👤 ፕሮፋይሌ"},
    "btn_transactions":{"en": "📋 Transactions",  "am": "📋 ግብይቶች"},
    "btn_balance":     {"en": "💰 Balance",       "am": "💰 ሂሳብ"},
    "btn_group":       {"en": "👥 Join Group",    "am": "👥 ቡድን ተቀላቀሉ"},
    "btn_contact":     {"en": "📞 Contact Us",    "am": "📞 ያግኙን"},
    "btn_refer":       {"en": "🎁 Refer & Earn",  "am": "🎁 ጋብዝ እና አትርፍ"},
    "btn_language":    {"en": "🌐 Switch to Amharic", "am": "🌐 ወደ እንግሊዝኛ ቀይር"},
    "btn_back":        {"en": "⬅️ Back",          "am": "⬅️ ተመለስ"},

    # ── Games menu ───────────────────────────────────────────────────────────
    "games_menu": {
        "en": "🎮 <b>Choose a Game</b>",
        "am": "🎮 <b>ጨዋታ ምረጥ</b>",
    },
    "coming_soon": {
        "en": "🔒 Coming Soon",
        "am": "🔒 በቅርቡ ይመጣል",
    },
    "players_online": {
        "en": "👥 {count} players",
        "am": "👥 {count} ተጫዋቾች",
    },

    # ── Room selection ────────────────────────────────────────────────────────
    "room_menu": {
        "en": "🎯 <b>Select a Room</b>\nChoose your entry fee:",
        "am": "🎯 <b>ክፍል ምረጥ</b>\nመክፈያ ምረጥ:",
    },
    "room_btn": {
        "en": "Bingo {fee} ETB | Pool: {pool} ETB",
        "am": "ቢንጎ {fee} ብር | ሽልማት: {pool} ብር",
    },

    # ── Card selection ────────────────────────────────────────────────────────
    "card_selection": {
        "en": (
            "🃏 <b>Room {fee} ETB — Card Selection</b>\n"
            "💰 Balance: <b>{balance} ETB</b>\n"
            "🏆 Prize Pool: <b>{pool} ETB</b>\n"
            "📦 Cards sold: <b>{sold}/200</b>\n"
            "⏱ Countdown: <b>{timer}s</b>\n"
            "👤 Last buy: <b>{last}</b>\n\n"
            "Select up to {max} cards. ✅ = yours  ⬛ = taken  ⬜ = free"
        ),
        "am": (
            "🃏 <b>ክፍል {fee} ብር — ካርድ ምረጥ</b>\n"
            "💰 ሂሳብ: <b>{balance} ብር</b>\n"
            "🏆 ሽልማት ገንዘብ: <b>{pool} ብር</b>\n"
            "📦 የተሸጡ ካርዶች: <b>{sold}/200</b>\n"
            "⏱ ቆጠራ: <b>{timer}ሰ</b>\n"
            "👤 የመጨረሻ ገዥ: <b>{last}</b>\n\n"
            "እስከ {max} ካርዶች ምረጥ። ✅ = ያንተ  ⬛ = የተወሰደ  ⬜ = ነፃ"
        ),
    },
    "page_indicator":  {"en": "Page {page}/{total}", "am": "ገጽ {page}/{total}"},
    "btn_random_x1":   {"en": "🎲 Random x1",       "am": "🎲 ዘፈቀደ x1"},
    "btn_random_x2":   {"en": "🎲 Random x2",       "am": "🎲 ዘፈቀደ x2"},
    "btn_start_game":  {"en": "▶️ START! ({n} cards — {cost} ETB)", "am": "▶️ ጀምር! ({n} ካርዶች — {cost} ብር)"},
    "no_cards_selected": {
        "en": "⚠️ Please select at least 1 card.",
        "am": "⚠️ ቢያንስ 1 ካርድ ምረጥ።",
    },
    "insufficient_balance": {
        "en": "❌ Insufficient balance. You need {need} ETB but have {have} ETB.",
        "am": "❌ በቂ ሂሳብ የለም። {need} ብር ያስፈልጋል ግን {have} ብር ብቻ አለህ።",
    },
    "cards_purchased": {
        "en": "✅ Cards {cards} purchased! Total: {cost} ETB deducted.",
        "am": "✅ ካርዶች {cards} ተገዙ! {cost} ብር ተቀንሷል።",
    },
    "card_taken": {
        "en": "⚠️ Card #{n} was just taken. It has been deselected.",
        "am": "⚠️ ካርድ #{n} ተወስዷል። ምርጫ ተሰርዟል።",
    },
    "max_cards_reached": {
        "en": "⚠️ You can only buy up to {max} cards per game.",
        "am": "⚠️ በአንድ ጨዋታ እስከ {max} ካርዶች ብቻ መግዛት ይቻላል።",
    },

    # ── Active game screen ────────────────────────────────────────────────────
    "game_screen": {
        "en": (
            "🎯 <b>Bingo {fee} ETB — Live Game</b>\n"
            "🏆 Pool: <b>{pool} ETB</b>   👥 <b>{players}</b> players\n"
            "📢 Call: <b>{called}/75</b>   🔔 Last: <b>{last_num}</b>\n\n"
            "<code>{number_grid}</code>\n\n"
            "🎱 Called: <b>{last_num}</b>"
        ),
        "am": (
            "🎯 <b>ቢንጎ {fee} ብር — ቀጥታ ጨዋታ</b>\n"
            "🏆 ሽልማት: <b>{pool} ብር</b>   👥 <b>{players}</b> ተጫዋቾች\n"
            "📢 ጥሪ: <b>{called}/75</b>   🔔 የመጨረሻ: <b>{last_num}</b>\n\n"
            "<code>{number_grid}</code>\n\n"
            "🎱 ተጠርቷል: <b>{last_num}</b>"
        ),
    },
    "btn_auto_on":  {"en": "🤖 Auto Win: ON",  "am": "🤖 ራስ-ሰር: አዎ"},
    "btn_auto_off": {"en": "🤖 Auto Win: OFF", "am": "🤖 ራስ-ሰር: አይ"},
    "btn_check":    {"en": "✅ Check All ({n}/{total})", "am": "✅ ሁሉ ፈትሽ ({n}/{total})"},
    "btn_bingo":    {"en": "🎉 BINGO!",          "am": "🎉 ቢንጎ!"},
    "waiting_start": {
        "en": "⏳ Waiting for game to start… ({sold} cards sold)",
        "am": "⏳ ጨዋታ ለመጀመር ተጠብቆ… ({sold} ካርዶች ተሸጡ)",
    },
    "countdown_started": {
        "en": "⏱ Game starts in <b>{sec}s</b>! {sold} cards sold.",
        "am": "⏱ ጨዋታ በ<b>{sec}ሰ</b> ይጀምራል! {sold} ካርዶች ተሸጡ።",
    },
    "game_starting": {
        "en": "🚀 Game is starting now!",
        "am": "🚀 ጨዋታ አሁን ይጀምራል!",
    },
    "number_called": {
        "en": "🔔 Number called: <b>{num}</b>",
        "am": "🔔 ቁጥር ተጠራ: <b>{num}</b>",
    },

    # ── Win / Game over ───────────────────────────────────────────────────────
    "you_won": {
        "en": (
            "🏆 <b>BINGO! You Won!</b>\n"
            "Card #{card} | {win_type}\n"
            "💰 Prize: <b>{prize} ETB</b> credited to your balance!"
        ),
        "am": (
            "🏆 <b>ቢንጎ! አሸነፍክ!</b>\n"
            "ካርድ #{card} | {win_type}\n"
            "💰 ሽልማት: <b>{prize} ብር</b> ወደ ሂሳብህ ተጨምሯል!"
        ),
    },
    "someone_won": {
        "en": (
            "🎊 <b>Game Over!</b>\n"
            "Winner: <b>{winner}</b>\n"
            "Card #{card} | {win_type}\n"
            "Prize: <b>{prize} ETB</b>"
        ),
        "am": (
            "🎊 <b>ጨዋታ ተጠናቀቀ!</b>\n"
            "አሸናፊ: <b>{winner}</b>\n"
            "ካርድ #{card} | {win_type}\n"
            "ሽልማት: <b>{prize} ብር</b>"
        ),
    },
    "no_winner_refund": {
        "en": "⚠️ No winner after 75 numbers. All players have been refunded.",
        "am": "⚠️ 75 ቁጥሮች ከጠሩ በኋላ አሸናፊ አልተገኘም። ለሁሉም ሰዎች ገንዘቡ ተመልሷል።",
    },
    "false_bingo": {
        "en": "❌ Invalid BINGO claim. Please check your card again.",
        "am": "❌ ያልተሟላ ቢንጎ። ካርድህን እንደገና ፈትሽ።",
    },
    "btn_play_again": {"en": "🔄 Play Again", "am": "🔄 እንደገና ጫወት"},
    "win_type_line":    {"en": "Line Win",    "am": "መስመር ድሉ"},
    "win_type_corners": {"en": "Corners Win", "am": "ማዕዘን ድሉ"},
    "not_in_game": {
        "en": "⚠️ You are not in an active game.",
        "am": "⚠️ አሁን ጨዋታ ውስጥ የሉም።",
    },

    # ── Lobby refund (< 2 cards) ──────────────────────────────────────────────
    "lobby_refund": {
        "en": "⏰ Timer expired with fewer than 2 cards sold. You have been refunded {amount} ETB.",
        "am": "⏰ 2 ካርዶች ሳይሸጡ ጊዜው አለቀ። {amount} ብር ተመልሷል።",
    },

    # ── Deposit ───────────────────────────────────────────────────────────────
    "deposit_choose_amount": {
        "en": "💰 <b>Deposit</b>\nChoose an amount or enter custom (min {min} ETB):",
        "am": "💰 <b>ተቀማጭ</b>\nገንዘብ ምረጥ ወይም ጻፍ (ቢያንስ {min} ብር):",
    },
    "deposit_instructions": {
        "en": (
            "📲 <b>Send {amount} ETB via Telebirr</b>\n\n"
            "Account: <b>{account_phone}</b>\n"
            "Name: <b>{account_name}</b>\n\n"
            "After sending, paste the <b>Telebirr SMS</b> you received:"
        ),
        "am": (
            "📲 <b>{amount} ብር በቴሌቢር ላክ</b>\n\n"
            "አካውንት: <b>{account_phone}</b>\n"
            "ስም: <b>{account_name}</b>\n\n"
            "ከላክ በኋላ የደረሰህን <b>ቴሌቢር SMS</b> ለጥፍ:"
        ),
    },
    "deposit_verifying": {
        "en": "🔍 Verifying your SMS…",
        "am": "🔍 SMS እየተረጋገጠ…",
    },
    "deposit_success": {
        "en": "✅ Deposit confirmed!\n💰 {amount} ETB added.\n💼 New balance: {balance} ETB",
        "am": "✅ ተቀማጭ ተረጋግጧል!\n💰 {amount} ብር ተጨምሯል።\n💼 አዲስ ሂሳብ: {balance} ብር",
    },
    "deposit_failed_parse": {
        "en": "❌ Could not read your SMS. Make sure you pasted the exact Telebirr message.",
        "am": "❌ SMS ማንበብ አልተቻለም። ትክክለኛውን ቴሌቢር SMS ቅጂ ያልጣፉ።",
    },
    "deposit_failed_recipient": {
        "en": "❌ Wrong recipient. Please send to the account shown above.",
        "am": "❌ የተሳሳተ ተቀባይ። ከላይ ለታየው አካውንት ብቻ ላክ።",
    },
    "deposit_failed_amount": {
        "en": "❌ Amount mismatch. SMS shows {sms_amount} ETB but you requested {req_amount} ETB.",
        "am": "❌ መጠን አይዛመድም። SMS {sms_amount} ብር ያሳያል ነገር ግን {req_amount} ብር ጠይቀሃል።",
    },
    "deposit_duplicate_ref": {
        "en": "❌ This transaction reference has already been used.",
        "am": "❌ ይህ ግብይት ቁጥር አስቀድሞ ጥቅም ላይ ውሏል።",
    },
    "deposit_cancelled": {
        "en": "❌ Deposit cancelled.",
        "am": "❌ ተቀማጭ ተሰርዟል።",
    },
    "invalid_amount": {
        "en": "❌ Invalid amount. Please enter a number ≥ {min} ETB.",
        "am": "❌ ትክክል ያልሆነ መጠን። {min} ብር ወይም ከዚያ በላይ ያስገቡ።",
    },

    # ── Withdrawal ────────────────────────────────────────────────────────────
    "withdraw_prompt": {
        "en": (
            "💸 <b>Withdraw</b>\n"
            "Account: <b>{phone}</b>\n"
            "Balance: <b>{balance} ETB</b>\n"
            "Min withdrawal: {min} ETB\n\n"
            "Enter amount:"
        ),
        "am": (
            "💸 <b>ማውጣት</b>\n"
            "አካውንት: <b>{phone}</b>\n"
            "ሂሳብ: <b>{balance} ብር</b>\n"
            "ዝቅተኛ ማውጣት: {min} ብር\n\n"
            "መጠን ያስገቡ:"
        ),
    },
    "withdraw_requested": {
        "en": "⏳ Withdrawal request submitted for {amount} ETB. You will be notified when approved.",
        "am": "⏳ {amount} ብር ለማውጣት ጥያቄ ተልኳል። ሲፈቀድ ትነገራለህ።",
    },
    "withdraw_no_phone": {
        "en": "⚠️ No phone number registered. Please update your profile first.",
        "am": "⚠️ ስልክ ቁጥር አልተመዘገበም። መጀመሪያ ፕሮፋይልህን አዘምን።",
    },

    # ── Transfer ──────────────────────────────────────────────────────────────
    "transfer_prompt_user": {
        "en": "💱 <b>Transfer</b>\nEnter recipient Telegram username (without @):",
        "am": "💱 <b>ማስተላለፍ</b>\nተቀባዩ Telegram ስም ያስገቡ (@ ሳይጨምሩ):",
    },
    "transfer_prompt_amount": {
        "en": "Enter amount to transfer (min {min} ETB, your balance: {balance} ETB):",
        "am": "ማስተላለፍ የሚፈልጉትን መጠን ያስገቡ (ቢያንስ {min} ብር, ሂሳብዎ: {balance} ብር):",
    },
    "transfer_success": {
        "en": "✅ Transferred {amount} ETB to @{to}. New balance: {balance} ETB",
        "am": "✅ {amount} ብር ወደ @{to} ተላልፏል። አዲስ ሂሳብ: {balance} ብር",
    },
    "transfer_received": {
        "en": "💰 You received {amount} ETB from @{from_user}!",
        "am": "💰 ከ @{from_user} {amount} ብር ደረሰህ!",
    },
    "transfer_cooldown": {
        "en": "⏱ You can transfer again in {mins} minutes.",
        "am": "⏱ ከ {mins} ደቂቃ በኋላ ማስተላለፍ ይቻላል።",
    },
    "transfer_user_not_found": {
        "en": "❌ User @{username} not found.",
        "am": "❌ @{username} አልተገኘም።",
    },
    "transfer_self": {
        "en": "❌ You cannot transfer to yourself.",
        "am": "❌ ለራሰህ ማስተላለፍ አይቻልም።",
    },

    # ── Profile ───────────────────────────────────────────────────────────────
    "profile": {
        "en": (
            "👤 <b>My Profile</b>\n\n"
            "🆔 ID: <code>{tid}</code>\n"
            "👤 Username: @{username}\n"
            "📱 Phone: {phone}\n"
            "💰 Balance: <b>{balance} ETB</b>\n"
            "🎮 Games Played: {games}\n"
            "🏆 Total Won: {won} ETB\n"
            "🎁 Referral Code: <code>{ref_code}</code>\n"
            "👥 Referred Friends: {ref_count}"
        ),
        "am": (
            "👤 <b>ፕሮፋይሌ</b>\n\n"
            "🆔 መለያ: <code>{tid}</code>\n"
            "👤 ስም: @{username}\n"
            "📱 ስልክ: {phone}\n"
            "💰 ሂሳብ: <b>{balance} ብር</b>\n"
            "🎮 የተጫወቱ ጨዋታዎች: {games}\n"
            "🏆 ጠቅላላ ያሸነፉ: {won} ብር\n"
            "🎁 ጥሪ ኮድ: <code>{ref_code}</code>\n"
            "👥 የጋበዙ ወዳጆች: {ref_count}"
        ),
    },

    # ── Transactions ──────────────────────────────────────────────────────────
    "transactions_header": {
        "en": "📋 <b>Last 10 Transactions</b>",
        "am": "📋 <b>የመጨረሻ 10 ግብይቶች</b>",
    },
    "tx_row": {
        "en": "{emoji} {type} — {amount} ETB — {date}",
        "am": "{emoji} {type} — {amount} ብር — {date}",
    },
    "no_transactions": {
        "en": "No transactions yet.",
        "am": "ምንም ግብይቶች የሉም።",
    },

    # ── Balance ───────────────────────────────────────────────────────────────
    "balance_msg": {
        "en": "💰 Your balance: <b>{balance} ETB</b>",
        "am": "💰 ሂሳብዎ: <b>{balance} ብር</b>",
    },

    # ── Referral ──────────────────────────────────────────────────────────────
    "referral_info": {
        "en": (
            "🎁 <b>Refer & Earn</b>\n\n"
            "Share your referral link and earn <b>{bonus} ETB</b> for each friend who joins!\n\n"
            "Your link: https://t.me/{bot}?start={code}\n"
            "Friends referred: {count}"
        ),
        "am": (
            "🎁 <b>ጋብዝ እና አትርፍ</b>\n\n"
            "ወዳጅህን ጋብዝ እያንዳንዱ ሲቀላቀል <b>{bonus} ብር</b> አትርፍ!\n\n"
            "ሊንክህ: https://t.me/{bot}?start={code}\n"
            "የጋበዙ ወዳጆች: {count}"
        ),
    },
    "referral_bonus_received": {
        "en": "🎁 Referral bonus! +{bonus} ETB added to your balance.",
        "am": "🎁 የጥሪ ሽልማት! +{bonus} ብር ወደ ሂሳብህ ተጨምሯል።",
    },

    # ── Admin panel ───────────────────────────────────────────────────────────
    "admin_menu": {
        "en": "⚙️ <b>Admin Panel</b>",
        "am": "⚙️ <b>አስተዳዳሪ ፓነል</b>",
    },
    "admin_stats": {
        "en": (
            "📊 <b>Dashboard</b>\n\n"
            "👥 Total Users: {users}\n"
            "🎮 Games Played: {games}\n"
            "💵 Total Collected: {collected} ETB\n"
            "🏦 House Profit (20%): {profit} ETB\n"
            "💸 Pending Withdrawals: {pending_wd}\n"
            "📥 Pending Deposits: {pending_dep}"
        ),
        "am": (
            "📊 <b>ዳሽቦርድ</b>\n\n"
            "👥 ጠቅላላ ተጠቃሚዎች: {users}\n"
            "🎮 የተጫወቱ ጨዋታዎች: {games}\n"
            "💵 ጠቅላላ የተሰበሰበ: {collected} ብር\n"
            "🏦 የቤቱ ትርፍ (20%): {profit} ብር\n"
            "💸 ወደ ፊት ፔንዲንግ ማውጣቶች: {pending_wd}\n"
            "📥 ፔንዲንግ ተቀማጮች: {pending_dep}"
        ),
    },
    "admin_withdrawal_item": {
        "en": "💸 #{wid} | @{user} | {amount} ETB | {phone}",
        "am": "💸 #{wid} | @{user} | {amount} ብር | {phone}",
    },
    "admin_approve_btn":  {"en": "✅ Approve #{wid}", "am": "✅ ፍቀድ #{wid}"},
    "admin_reject_btn":   {"en": "❌ Reject #{wid}",  "am": "❌ ሰርዝ #{wid}"},
    "withdrawal_approved": {
        "en": "✅ Withdrawal #{wid} approved. {amount} ETB sent to {phone}.",
        "am": "✅ ማውጣት #{wid} ፈቀደ። {amount} ብር ወደ {phone} ተላለፈ።",
    },
    "withdrawal_rejected": {
        "en": "❌ Withdrawal #{wid} rejected.",
        "am": "❌ ማውጣት #{wid} ተሰረዘ።",
    },
    "withdrawal_notify_approved": {
        "en": "✅ Your withdrawal of {amount} ETB has been approved!",
        "am": "✅ የ {amount} ብር ማውጣትዎ ፈቅዷል!",
    },
    "withdrawal_notify_rejected": {
        "en": "❌ Your withdrawal of {amount} ETB was rejected. Amount refunded.",
        "am": "❌ የ {amount} ብር ማውጣትዎ ተሰርዟል። ገንዘቡ ተመልሷል።",
    },
    "no_pending_withdrawals": {
        "en": "✅ No pending withdrawals.",
        "am": "✅ ምንም ፔንዲንግ ማውጣቶች የሉም።",
    },
    "admin_deposit_accounts": {
        "en": "🏦 <b>Deposit Accounts</b>\nSend account in format: <code>phone|name</code> to add.\nSend ID to remove.",
        "am": "🏦 <b>ተቀማጭ አካውንቶች</b>\nለማከል: <code>ስልክ|ስም</code> ቅርጸት ይላኩ። ለማስወገድ: ID ይላኩ።",
    },
    "broadcast_prompt": {
        "en": "📢 Send the message/photo you want to broadcast to all users:",
        "am": "📢 ለሁሉም ተጠቃሚዎች ማሰራጨት የሚፈልጉትን መልዕክት/ፎቶ ይላኩ:",
    },
    "broadcast_done": {
        "en": "✅ Broadcast sent to {count} users.",
        "am": "✅ ለ {count} ተጠቃሚዎች ተልኳል።",
    },
    "not_admin": {
        "en": "❌ Unauthorized.",
        "am": "❌ ፍቃድ የለዎትም።",
    },

    # ── Generic errors ────────────────────────────────────────────────────────
    "error_generic": {
        "en": "⚠️ Something went wrong. Please try again.",
        "am": "⚠️ ችግር ተፈጥሯል። እንደገና ሞክር።",
    },
    "cancelled": {
        "en": "❌ Cancelled.",
        "am": "❌ ተሰርዟል።",
    },
}


def get_text(key: str, lang: str = "en", **kwargs) -> str:
    """Return translated string, formatted with kwargs. Falls back to English."""
    entry = STRINGS.get(key, {})
    text = entry.get(lang) or entry.get("en") or f"[{key}]"
    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            pass
    return text
