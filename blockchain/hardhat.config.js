require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config();

const { SEPOLIA_RPC_URL, PRIVATE_KEY } = process.env;

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.24",
    settings: { optimizer: { enabled: true, runs: 200 } },
  },
  networks: {
    hardhat: {},
    // 테스트넷 배포용 (.env 에 RPC URL/키 설정)
    sepolia: SEPOLIA_RPC_URL && PRIVATE_KEY
      ? { url: SEPOLIA_RPC_URL, accounts: [PRIVATE_KEY] }
      : undefined,
  },
};
