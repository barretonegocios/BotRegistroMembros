import os

ENV_FILE = ".env"

def main():
    print("=" * 45)
    print("   BC SYSTEM - Configuração do Token")
    print("=" * 45)

    token_atual = ""
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r") as f:
            for linha in f:
                if linha.startswith("DISCORD_TOKEN="):
                    token_atual = linha.split("=", 1)[1].strip()

    if token_atual and token_atual != "seu_token_aqui":
        print(f"\nToken atual: {token_atual[:20]}...")
        substituir = input("Deseja substituir? (s/n): ").strip().lower()
        if substituir != "s":
            print("\nOperação cancelada.")
            input("\nPressione Enter para sair...")
            return

    print("\nCole o token do seu bot Discord abaixo:")
    token = input("Token: ").strip()

    if not token:
        print("\n❌ Token inválido. Operação cancelada.")
        input("\nPressione Enter para sair...")
        return

    with open(ENV_FILE, "w") as f:
        f.write(f"DISCORD_TOKEN={token}\n")

    print("\n✅ Token salvo com sucesso!")
    print("   Execute iniciar_bot.bat para iniciar o bot.")
    input("\nPressione Enter para sair...")

if __name__ == "__main__":
    main()
