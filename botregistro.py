import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import os
import json
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

CONFIG_FILE = "config.json"
REGISTROS_FILE = "registros.json"

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ─── Persistência ────────────────────────────────────────────────────────────

def carregar_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def salvar_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def carregar_registros():
    if not os.path.exists(REGISTROS_FILE):
        return {}
    with open(REGISTROS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def salvar_registros(data):
    with open(REGISTROS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── Seleção de Cargo ────────────────────────────────────────────────────────

class SelectCargo(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Membro",
                value="Membro",
                emoji="👤",
                description="Cargo padrão de membro"
            )
        ]
        super().__init__(placeholder="Selecione o cargo...", options=options)

    async def callback(self, interaction: discord.Interaction):
        self.view.cargo_selecionado = self.values[0]
        await interaction.response.defer()


class ViewSelecionarCargo(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.cargo_selecionado = None
        self.add_item(SelectCargo())

    @discord.ui.button(label="Continuar →", style=discord.ButtonStyle.primary)
    async def continuar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.cargo_selecionado:
            await interaction.response.send_message(
                "⚠️ Selecione um cargo antes de continuar.", ephemeral=True
            )
            return
        await interaction.response.send_modal(ModalRegistro(cargo=self.cargo_selecionado))


# ─── Modal de Registro ────────────────────────────────────────────────────────

class ModalRegistro(discord.ui.Modal, title="📋 Registro de Membro"):
    nome_rp = discord.ui.TextInput(
        label="Nome do RP",
        placeholder="Ex: João Silva",
        max_length=80
    )
    id_jogador = discord.ui.TextInput(
        label="ID",
        placeholder="Ex: 12345",
        max_length=20
    )
    telefone = discord.ui.TextInput(
        label="Telefone",
        placeholder="Ex: (11) 99999-9999",
        max_length=20
    )
    quem_contratou = discord.ui.TextInput(
        label="Quem te contratou?",
        placeholder="Nome do recrutador",
        max_length=80
    )

    def __init__(self, cargo: str):
        super().__init__()
        self.cargo = cargo

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        member_id = str(interaction.user.id)

        config = carregar_config()
        if guild_id not in config:
            await interaction.response.send_message(
                "❌ Bot não configurado. Peça ao administrador para usar `/setup_registro`.",
                ephemeral=True
            )
            return

        cfg = config[guild_id]
        canal_aprovacao_id = cfg.get("canal_aprovacao_id")
        if not canal_aprovacao_id:
            await interaction.response.send_message(
                "❌ Canal de aprovação não configurado.", ephemeral=True
            )
            return

        registros = carregar_registros()
        if guild_id not in registros:
            registros[guild_id] = {}

        # Verifica se já tem registro pendente ou aprovado
        if member_id in registros[guild_id]:
            status = registros[guild_id][member_id].get("status")
            if status == "pendente":
                await interaction.response.send_message(
                    "⏳ Você já possui um registro aguardando aprovação!", ephemeral=True
                )
                return
            if status == "aprovado":
                await interaction.response.send_message(
                    "✅ Você já foi aprovado no servidor!", ephemeral=True
                )
                return

        dados = {
            "nome_rp": self.nome_rp.value,
            "id": self.id_jogador.value,
            "telefone": self.telefone.value,
            "quem_contratou": self.quem_contratou.value,
            "cargo": self.cargo,
        }

        registros[guild_id][member_id] = {
            "status": "pendente",
            "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "dados": dados,
            "aprovado_por": None,
            "mensagem_id": None,
        }
        salvar_registros(registros)

        # Envia para canal de aprovação
        canal = interaction.guild.get_channel(canal_aprovacao_id)
        if not canal:
            await interaction.response.send_message(
                "❌ Canal de aprovação não encontrado.", ephemeral=True
            )
            return

        embed = _embed_registro(interaction.user, dados, registros[guild_id][member_id]["data"])
        view = ViewAprovacao(member_id=member_id, guild_id=guild_id)
        msg = await canal.send(embed=embed, view=view)

        registros[guild_id][member_id]["mensagem_id"] = msg.id
        salvar_registros(registros)

        await interaction.response.send_message(
            "✅ Registro enviado! Aguarde a aprovação dos gerentes.", ephemeral=True
        )


def _embed_registro(member: discord.Member, dados: dict, data: str) -> discord.Embed:
    embed = discord.Embed(
        title="📋 Novo Registro de Membro",
        description=f"**{member.mention}** solicitou entrada no servidor.",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🎭 Nome do RP", value=dados["nome_rp"], inline=True)
    embed.add_field(name="🪪 ID", value=dados["id"], inline=True)
    embed.add_field(name="📞 Telefone", value=dados["telefone"], inline=True)
    embed.add_field(name="🤝 Quem contratou", value=dados["quem_contratou"], inline=True)
    embed.add_field(name="🏅 Cargo", value=dados["cargo"], inline=True)
    embed.set_footer(text=f"Discord ID: {member.id} • Enviado em {data}")
    return embed


# ─── Views de Aprovação ───────────────────────────────────────────────────────

def _e_aprovador(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    if member.guild.owner_id == member.id:
        return True
    perms = member.guild_permissions
    return perms.manage_guild or perms.manage_roles


class ModalNegacao(discord.ui.Modal, title="❌ Motivo da Negação"):
    motivo = discord.ui.TextInput(
        label="Motivo",
        placeholder="Explique o motivo da negação...",
        style=discord.TextStyle.paragraph,
        max_length=400
    )

    def __init__(self, member_id: str, guild_id: str):
        super().__init__()
        self.member_id = member_id
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        registros = carregar_registros()
        reg = registros.get(self.guild_id, {}).get(self.member_id)
        if not reg or reg["status"] != "pendente":
            await interaction.response.send_message(
                "⚠️ Registro não encontrado ou já processado.", ephemeral=True
            )
            return

        reg["status"] = "negado"
        reg["aprovado_por"] = str(interaction.user.id)
        reg["motivo_negacao"] = self.motivo.value
        salvar_registros(registros)

        # Busca a mensagem de aprovação para editar
        config = carregar_config()
        canal_id = config.get(self.guild_id, {}).get("canal_aprovacao_id")
        msg_id = reg.get("mensagem_id")
        if canal_id and msg_id:
            canal = interaction.guild.get_channel(canal_id)
            if canal:
                try:
                    mensagem = await canal.fetch_message(msg_id)
                    embed = mensagem.embeds[0]
                    embed.color = discord.Color.red()
                    embed.add_field(
                        name="❌ Negado por",
                        value=f"{interaction.user.mention}\n**Motivo:** {self.motivo.value}",
                        inline=False
                    )
                    await mensagem.edit(embed=embed, view=None)
                except Exception:
                    pass

        # Notifica o membro por DM
        guild = interaction.guild
        membro = guild.get_member(int(self.member_id))
        if membro:
            try:
                dm_embed = discord.Embed(
                    title="❌ Registro Negado",
                    description=f"Seu registro em **{guild.name}** foi negado.",
                    color=discord.Color.red()
                )
                dm_embed.add_field(name="Motivo", value=self.motivo.value)
                dm_embed.set_footer(text="Entre em contato com a administração caso tenha dúvidas.")
                await membro.send(embed=dm_embed)
            except discord.Forbidden:
                pass

        await interaction.response.send_message(
            f"✅ Registro de **{reg['dados']['nome_rp']}** negado.", ephemeral=True
        )


class BotaoAprovar(discord.ui.Button):
    def __init__(self, member_id: str, guild_id: str):
        super().__init__(
            label="✅ Aprovar",
            style=discord.ButtonStyle.success,
            custom_id=f"aprovar_{guild_id}_{member_id}"
        )

    async def callback(self, interaction: discord.Interaction):
        partes = self.custom_id.split("_", 2)
        if len(partes) != 3:
            await interaction.response.send_message("❌ Erro interno no botão.", ephemeral=True)
            return

        _, guild_id, member_id = partes
        registros = carregar_registros()
        reg = registros.get(guild_id, {}).get(member_id)

        if not _e_aprovador(interaction.user):
            await interaction.response.send_message(
                "❌ Você não tem permissão para aprovar registros.", ephemeral=True
            )
            return

        if not reg or reg["status"] != "pendente":
            await interaction.response.send_message(
                "⚠️ Registro não encontrado ou já processado.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        config = carregar_config()
        cfg = config.get(guild_id, {})
        guild = interaction.guild
        membro = guild.get_member(int(member_id))

        cargo_id = cfg.get("cargo_aprovado_id")
        cargo_pendente_id = cfg.get("cargo_pendente_id")
        avisos = []

        if membro and cargo_id:
            cargo = guild.get_role(cargo_id)
            if cargo:
                try:
                    await membro.add_roles(cargo, reason="Registro aprovado")
                except discord.Forbidden:
                    avisos.append("⚠️ Não foi possível dar o cargo (verifique a hierarquia de cargos do bot).")

        if membro and cargo_pendente_id:
            cargo_pendente = guild.get_role(cargo_pendente_id)
            if cargo_pendente:
                try:
                    await membro.remove_roles(cargo_pendente, reason="Registro aprovado")
                except discord.Forbidden:
                    pass

        # Muda o nickname para o nome do RP
        if membro:
            try:
                await membro.edit(nick=f"{reg['dados']['nome_rp']} | {reg['dados']['id']}", reason="Nickname de RP aplicado")
            except discord.Forbidden:
                avisos.append("⚠️ Não foi possível alterar o nickname (verifique as permissões do bot).")

        reg["status"] = "aprovado"
        reg["aprovado_por"] = str(interaction.user.id)
        salvar_registros(registros)

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.add_field(name="✅ Aprovado por", value=interaction.user.mention, inline=False)
        await interaction.message.edit(embed=embed, view=None)

        if membro:
            try:
                dm_embed = discord.Embed(
                    title="✅ Registro Aprovado!",
                    description=f"Seu registro em **{guild.name}** foi aprovado! Bem-vindo(a)! 🎉",
                    color=discord.Color.green()
                )
                dm_embed.set_footer(text="Aproveite o servidor!")
                await membro.send(embed=dm_embed)
            except discord.Forbidden:
                pass

        canal_notif_id = cfg.get("canal_notificacao_id")
        if canal_notif_id:
            canal = guild.get_channel(canal_notif_id)
            if canal and membro:
                notif_embed = discord.Embed(
                    description=f"🎉 {membro.mention} foi aprovado(a) no servidor por {interaction.user.mention}!",
                    color=discord.Color.green()
                )
                await canal.send(embed=notif_embed)

        msg = f"✅ **{reg['dados']['nome_rp']}** aprovado(a) com sucesso!"
        if avisos:
            msg += "\n" + "\n".join(avisos)
        await interaction.followup.send(msg, ephemeral=True)


class BotaoNegar(discord.ui.Button):
    def __init__(self, member_id: str, guild_id: str):
        super().__init__(
            label="❌ Negar",
            style=discord.ButtonStyle.danger,
            custom_id=f"negar_{guild_id}_{member_id}"
        )

    async def callback(self, interaction: discord.Interaction):
        _, guild_id, member_id = self.custom_id.split("_", 2)

        if not _e_aprovador(interaction.user):
            await interaction.response.send_message(
                "❌ Você não tem permissão para negar registros.", ephemeral=True
            )
            return

        registros = carregar_registros()
        reg = registros.get(guild_id, {}).get(member_id)
        if not reg or reg["status"] != "pendente":
            await interaction.response.send_message(
                "⚠️ Registro não encontrado ou já processado.", ephemeral=True
            )
            return

        await interaction.response.send_modal(ModalNegacao(member_id=member_id, guild_id=guild_id))


class ViewAprovacao(discord.ui.View):
    def __init__(self, member_id: str, guild_id: str):
        super().__init__(timeout=None)
        self.add_item(BotaoAprovar(member_id, guild_id))
        self.add_item(BotaoNegar(member_id, guild_id))


# ─── Botão de Registro no Canal ───────────────────────────────────────────────

class ViewRegistrar(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📋 Registrar",
        style=discord.ButtonStyle.primary,
        custom_id="registrar_me_btn"
    )
    async def registrar_me(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "**Selecione seu cargo e clique em Continuar:**",
            view=ViewSelecionarCargo(),
            ephemeral=True
        )


# ─── Eventos ──────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    bot.add_view(ViewRegistrar())
    registros = carregar_registros()
    for guild_id, guild_regs in registros.items():
        for member_id, reg in guild_regs.items():
            if reg["status"] == "pendente":
                bot.add_view(ViewAprovacao(member_id=member_id, guild_id=guild_id))
    # Copia comandos globais para cada servidor
    for guild in bot.guilds:
        bot.tree.copy_global_to(guild=guild)

    # Remove comandos globais do Discord (evita duplicatas)
    bot.tree.clear_commands(guild=None)
    await bot.tree.sync()

    # Sincroniza apenas como comandos de servidor (instantâneo)
    for guild in bot.guilds:
        try:
            gs = await bot.tree.sync(guild=guild)
            print(f"[{guild.name}] {len(gs)} comandos.", flush=True)
        except Exception as e:
            print(f"[{guild.name}] Erro: {e}", flush=True)
    print(f"Bot {bot.user} online!", flush=True)


@bot.event
async def on_member_join(member: discord.Member):
    guild_id = str(member.guild.id)
    member_id = str(member.id)

    # Reseta o registro ao entrar novamente (ex: após ser expulso)
    registros = carregar_registros()
    if guild_id in registros and member_id in registros[guild_id]:
        del registros[guild_id][member_id]
        salvar_registros(registros)

    config = carregar_config()
    cfg = config.get(guild_id, {})

    # Atribui cargo pendente se configurado
    cargo_pendente_id = cfg.get("cargo_pendente_id")
    if cargo_pendente_id:
        cargo = member.guild.get_role(cargo_pendente_id)
        if cargo:
            try:
                await member.add_roles(cargo, reason="Aguardando aprovação de registro")
            except discord.Forbidden:
                pass

    # Manda DM com instruções
    canal_registro_id = cfg.get("canal_registro_id")
    if not canal_registro_id:
        return

    try:
        embed = discord.Embed(
            title=f"👋 Bem-vindo(a) ao {member.guild.name}!",
            description=(
                f"Olá {member.mention}! Para ter acesso completo ao servidor, "
                f"você precisa se registrar.\n\n"
                f"Vá até o canal de registro e clique em **📋 Registrar-me**!"
            ),
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=member.guild.icon.url if member.guild.icon else None)
        await member.send(embed=embed)
    except discord.Forbidden:
        pass


# ─── Comandos de Configuração ─────────────────────────────────────────────────

@bot.tree.command(name="setup_registro", description="Configura o bot de registro de membros")
@app_commands.describe(
    canal_aprovacao="Canal onde os registros chegam para aprovação",
    canal_registro="Canal onde fica o botão de registro",
    cargo_aprovado="Cargo dado ao membro após aprovação",
    cargo_pendente="Cargo dado ao membro enquanto aguarda aprovação (opcional)",
    canal_notificacao="Canal para anunciar aprovações (opcional)"
)
@app_commands.checks.has_permissions(administrator=True)
async def setup_registro(
    interaction: discord.Interaction,
    canal_aprovacao: discord.TextChannel,
    canal_registro: discord.TextChannel,
    cargo_aprovado: discord.Role,
    cargo_pendente: discord.Role = None,
    canal_notificacao: discord.TextChannel = None
):
    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild.id)
    config = carregar_config()

    config[guild_id] = {
        "canal_aprovacao_id": canal_aprovacao.id,
        "canal_registro_id": canal_registro.id,
        "cargo_aprovado_id": cargo_aprovado.id,
        "cargo_pendente_id": cargo_pendente.id if cargo_pendente else None,
        "canal_notificacao_id": canal_notificacao.id if canal_notificacao else None,
    }
    salvar_config(config)

    embed = discord.Embed(
        title="✅ Bot de Registro Configurado!",
        color=discord.Color.green()
    )
    embed.add_field(name="📥 Canal de Aprovação", value=canal_aprovacao.mention, inline=True)
    embed.add_field(name="📋 Canal de Registro", value=canal_registro.mention, inline=True)
    embed.add_field(name="🏅 Cargo Aprovado", value=cargo_aprovado.mention, inline=True)
    if cargo_pendente:
        embed.add_field(name="⏳ Cargo Pendente", value=cargo_pendente.mention, inline=True)
    if canal_notificacao:
        embed.add_field(name="📢 Canal de Notificação", value=canal_notificacao.mention, inline=True)

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="painel_registro", description="Envia o painel de registro no canal atual")
@app_commands.checks.has_permissions(administrator=True)
async def painel_registro(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild.id)
    config = carregar_config()
    if guild_id not in config:
        await interaction.followup.send(
            "❌ Configure o bot primeiro com `/setup_registro`.", ephemeral=True
        )
        return

    embed = discord.Embed(
        title="🗂️ Registro de Membros",
        description=(
            "Você está prestes a iniciar o processo de **registro oficial** no servidor.\n\n"
            "• 🧩 Apenas membros **ainda não registrados** podem se registrar.\n"
            "• 🕵️ Após o registro, a equipe verificará suas informações.\n\n"
            "> Clique no botão abaixo para começar."
        ),
        color=discord.Color.blue()
    )
    embed.set_author(name="BC SYSTEM • Sistema de Registro", icon_url=bot.user.display_avatar.url)
    embed.set_footer(text="Sistema de Registro • Automático")

    await interaction.channel.send(embed=embed, view=ViewRegistrar())
    await interaction.followup.send("✅ Painel enviado!", ephemeral=True)


@bot.tree.command(name="ver_registros", description="Lista registros pendentes do servidor")
@app_commands.checks.has_permissions(manage_guild=True)
async def ver_registros(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild.id)
    registros = carregar_registros()
    guild_regs = registros.get(guild_id, {})

    pendentes = [
        (mid, r) for mid, r in guild_regs.items() if r["status"] == "pendente"
    ]

    if not pendentes:
        await interaction.followup.send("✅ Nenhum registro pendente!", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"⏳ Registros Pendentes ({len(pendentes)})",
        color=discord.Color.orange()
    )
    for mid, reg in pendentes[:10]:
        member = interaction.guild.get_member(int(mid))
        nome_discord = member.mention if member else f"<@{mid}>"
        embed.add_field(
            name=f"{reg['dados']['nome_rp']}",
            value=f"{nome_discord} • {reg['data']}",
            inline=False
        )

    if len(pendentes) > 10:
        embed.set_footer(text=f"Mostrando 10 de {len(pendentes)} pendentes.")

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="resetar_registro", description="Remove o registro de um membro (permite novo envio)")
@app_commands.describe(membro="Membro para resetar o registro")
@app_commands.checks.has_permissions(administrator=True)
async def resetar_registro(interaction: discord.Interaction, membro: discord.Member):
    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild.id)
    registros = carregar_registros()

    if guild_id in registros and str(membro.id) in registros[guild_id]:
        del registros[guild_id][str(membro.id)]
        salvar_registros(registros)
        await interaction.followup.send(
            f"✅ Registro de {membro.mention} removido. Ele(a) pode se registrar novamente.",
            ephemeral=True
        )
    else:
        await interaction.followup.send(
            f"⚠️ Nenhum registro encontrado para {membro.mention}.", ephemeral=True
        )


@bot.tree.command(name="limpar_aprovacoes", description="Apaga todas as mensagens do bot no canal de aprovação")
@app_commands.checks.has_permissions(administrator=True)
async def limpar_aprovacoes(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild.id)
    config = carregar_config()
    canal_id = config.get(guild_id, {}).get("canal_aprovacao_id")

    if not canal_id:
        await interaction.followup.send("❌ Canal de aprovação não configurado.", ephemeral=True)
        return

    canal = interaction.guild.get_channel(canal_id)
    if not canal:
        await interaction.followup.send("❌ Canal não encontrado.", ephemeral=True)
        return

    deletadas = await canal.purge(limit=200, check=lambda m: m.author == bot.user)
    await interaction.followup.send(
        f"✅ {len(deletadas)} mensagem(ns) deletada(s) no canal {canal.mention}.",
        ephemeral=True
    )


# ─── Hierarquia de Cargos ────────────────────────────────────────────────────

def _embed_hierarquia(guild: discord.Guild) -> discord.Embed:
    config = carregar_config()
    cargos_ids = config.get(str(guild.id), {}).get("cargos_hierarquia")

    todos = sorted(
        [r for r in guild.roles if r.name != "@everyone"],
        key=lambda r: r.position,
        reverse=True
    )

    if cargos_ids:
        roles = [r for r in todos if r.id in cargos_ids]
    else:
        roles = todos

    embed = discord.Embed(
        title="BC SYSTEM — Hierarquia de Cargos",
        color=discord.Color.blue()
    )

    roles_com_membros = [r for r in roles if r.members]

    if not roles_com_membros:
        embed.description = "Nenhum cargo com membros encontrado."
    else:
        for i, role in enumerate(roles_com_membros[:12]):
            membros_txt = "\n".join(
                f"- {m.mention}" for m in sorted(role.members, key=lambda m: m.display_name)
            )
            embed.add_field(
                name=f"● {role.name}",
                value=membros_txt[:1024],
                inline=False
            )
            if i < len(roles_com_membros) - 1:
                embed.add_field(name="​", value="​", inline=False)

    embed.set_footer(text=f"Atualizado em: {datetime.now().strftime('%d/%m/%Y, %H:%M:%S')}")
    return embed


async def _atualizar_hierarquia(guild: discord.Guild):
    config = carregar_config()
    guild_id = str(guild.id)
    cfg = config.get(guild_id, {})

    canal_id = cfg.get("canal_hierarquia_id")
    if not canal_id:
        return

    canal = guild.get_channel(canal_id)
    if not canal:
        return

    if not guild.chunked:
        await guild.chunk()

    embed = _embed_hierarquia(guild)
    msg_id = cfg.get("mensagem_hierarquia_id")

    if msg_id:
        try:
            msg = await canal.fetch_message(msg_id)
            await msg.edit(embed=embed)
            return
        except discord.NotFound:
            pass

    await canal.purge(limit=10, check=lambda m: m.author == guild.me)
    msg = await canal.send(embed=embed)
    config[guild_id]["mensagem_hierarquia_id"] = msg.id
    salvar_config(config)


@bot.tree.command(name="setup_hierarquia", description="Configura o canal de hierarquia de cargos")
@app_commands.describe(canal="Canal onde a hierarquia será exibida")
@app_commands.checks.has_permissions(administrator=True)
async def setup_hierarquia(interaction: discord.Interaction, canal: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild.id)
    config = carregar_config()
    if guild_id not in config:
        config[guild_id] = {}

    config[guild_id]["canal_hierarquia_id"] = canal.id
    config[guild_id]["mensagem_hierarquia_id"] = None
    salvar_config(config)

    await _atualizar_hierarquia(interaction.guild)
    await interaction.followup.send(
        f"✅ Hierarquia configurada em {canal.mention}!", ephemeral=True
    )


@bot.event
async def on_guild_role_create(role: discord.Role):
    await _atualizar_hierarquia(role.guild)


@bot.event
async def on_guild_role_delete(role: discord.Role):
    await _atualizar_hierarquia(role.guild)


@bot.event
async def on_guild_role_update(before: discord.Role, after: discord.Role):
    await _atualizar_hierarquia(after.guild)


@bot.event
async def on_member_update(_before: discord.Member, after: discord.Member):
    if _before.roles != after.roles:
        await _atualizar_hierarquia(after.guild)


# ─── Seleção de Cargos da Hierarquia ─────────────────────────────────────────

class SelectCargosHierarquia(discord.ui.Select):
    def __init__(self, guild: discord.Guild, selecionados: list):
        roles = sorted(
            [r for r in guild.roles if r.name != "@everyone"],
            key=lambda r: r.position,
            reverse=True
        )
        options = [
            discord.SelectOption(
                label=role.name[:100],
                value=str(role.id),
                default=role.id in selecionados
            )
            for role in roles[:25]
        ]
        super().__init__(
            placeholder="Selecione os cargos para exibir...",
            options=options,
            min_values=1,
            max_values=len(options)
        )

    async def callback(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        config = carregar_config()
        if guild_id not in config:
            config[guild_id] = {}
        config[guild_id]["cargos_hierarquia"] = [int(v) for v in self.values]
        salvar_config(config)
        await _atualizar_hierarquia(interaction.guild)
        nomes = [interaction.guild.get_role(int(v)).name for v in self.values if interaction.guild.get_role(int(v))]
        await interaction.response.send_message(
            f"✅ Hierarquia atualizada com **{len(self.values)}** cargo(s):\n" +
            "\n".join(f"• {n}" for n in nomes),
            ephemeral=True
        )


class ViewConfigHierarquia(discord.ui.View):
    def __init__(self, guild: discord.Guild, selecionados: list):
        super().__init__(timeout=60)
        self.add_item(SelectCargosHierarquia(guild, selecionados))


@bot.tree.command(name="config_hierarquia", description="Seleciona quais cargos aparecem na hierarquia")
@app_commands.checks.has_permissions(administrator=True)
async def config_hierarquia(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    config = carregar_config()
    selecionados = config.get(guild_id, {}).get("cargos_hierarquia", [])

    await interaction.response.send_message(
        "Selecione os cargos que devem aparecer na hierarquia:",
        view=ViewConfigHierarquia(interaction.guild, selecionados),
        ephemeral=True
    )


# ─── Error Handlers ───────────────────────────────────────────────────────────

@setup_registro.error
@painel_registro.error
@ver_registros.error
@resetar_registro.error
@limpar_aprovacoes.error
@setup_hierarquia.error
@config_hierarquia.error
async def on_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ Você não tem permissão para usar este comando.", ephemeral=True
        )
    else:
        with open("bot_errors.log", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] {error}\n")
        try:
            await interaction.response.send_message(
                "❌ Ocorreu um erro. Tente novamente.", ephemeral=True
            )
        except Exception:
            pass


# ─── Start ────────────────────────────────────────────────────────────────────

bot.run(TOKEN)

