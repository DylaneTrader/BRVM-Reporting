import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

const DEFAULT_USER_NAME = "local";
const INITIAL_CASH = parseFloat(process.env.INITIAL_CASH || "1000000");

async function main() {
  const user = await prisma.user.upsert({
    where: { name: DEFAULT_USER_NAME },
    update: {},
    create: { name: DEFAULT_USER_NAME },
  });

  const existing = await prisma.portfolio.findUnique({
    where: { userId: user.id },
  });
  if (existing) {
    console.log("Portefeuille déjà initialisé. Rien à faire.");
    return;
  }

  await prisma.portfolio.create({
    data: {
      userId: user.id,
      cash: INITIAL_CASH,
      transactions:
        INITIAL_CASH > 0
          ? {
              create: {
                type: "DEPOSIT",
                fees: 0,
                cashDelta: INITIAL_CASH,
                cashAfter: INITIAL_CASH,
              },
            }
          : undefined,
    },
  });

  console.log(
    `Portefeuille créé pour "${DEFAULT_USER_NAME}" avec ${INITIAL_CASH} FCFA.`
  );
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
