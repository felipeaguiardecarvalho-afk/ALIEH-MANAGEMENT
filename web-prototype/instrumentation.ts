export async function register() {

  if (process.env.NEXT_RUNTIME !== "nodejs") {

    return;

  }

  const {

    getAliehEnv,

    assertProductionServerEnv,

    assertStagingServerEnv,

    assertStrictQaOrchestrationEnv,

  } = await import("@/lib/env/alieh-runtime");



  assertStrictQaOrchestrationEnv();



  const tier = getAliehEnv();

  if (tier === "production") {

    assertProductionServerEnv();

  } else if (tier === "staging") {

    assertStagingServerEnv();

  }



  if (tier === "production" || tier === "staging") {

    const { getPrototypeApiBase } = await import("@/lib/api-prototype");

    getPrototypeApiBase();

  }

}

