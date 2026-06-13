const { expect } = require("chai");
const { ethers } = require("hardhat");

// 핵심 시나리오: 등록(동의 프로비넌스) → 라이선스 결제 → 로열티 분배/인출 → 세션 사용료 → 스테이킹/투표
describe("VoiceCoin 생태계", function () {
  let coin, registry, license, staking;
  let owner, creator, learner, treasury;
  const e18 = (n) => ethers.parseUnits(n.toString(), 18);

  beforeEach(async () => {
    [owner, creator, learner, treasury] = await ethers.getSigners();

    const Coin = await ethers.getContractFactory("VoiceCoin");
    coin = await Coin.deploy(e18(1_000_000_000), e18(100_000_000), owner.address);

    const Registry = await ethers.getContractFactory("VoiceRegistry");
    registry = await Registry.deploy("ipfs://base/");

    const License = await ethers.getContractFactory("VoiceLicense");
    license = await License.deploy(await coin.getAddress(), await registry.getAddress(), treasury.address);

    const Staking = await ethers.getContractFactory("VoiceStaking");
    staking = await Staking.deploy(await coin.getAddress(), e18(1000));

    // 학습자에게 토큰 지급
    await coin.transfer(learner.address, e18(10000));
  });

  it("동의 해시 없이는 등록 불가", async () => {
    await expect(
      registry.connect(creator).registerVoice(ethers.ZeroHash, "American", e18(100), e18(1), 8000)
    ).to.be.revertedWith("consent required");
  });

  it("등록 → NFT 소유 + 프로비넌스 기록", async () => {
    const consent = ethers.keccak256(ethers.toUtf8Bytes("consent-record-v1"));
    await registry.connect(creator).registerVoice(consent, "British", e18(100), e18(1), 8000);
    expect(await registry.ownerOf(1)).to.equal(creator.address);
    const v = await registry.voices(1);
    expect(v.consentHash).to.equal(consent);
    expect(v.accent).to.equal("British");
  });

  it("라이선스 결제 → 로열티 80% 소유자, 20% 트레저리", async () => {
    const consent = ethers.keccak256(ethers.toUtf8Bytes("c"));
    await registry.connect(creator).registerVoice(consent, "American", e18(100), e18(1), 8000);

    await coin.connect(learner).approve(await license.getAddress(), e18(100));
    await license.connect(learner).buyLicense(1);

    expect(await license.hasLicense(1, learner.address)).to.equal(true);
    expect(await license.royaltiesOwed(creator.address)).to.equal(e18(80));
    expect(await coin.balanceOf(treasury.address)).to.equal(e18(20));

    // 소유자 인출
    await license.connect(creator).withdrawRoyalties();
    expect(await coin.balanceOf(creator.address)).to.equal(e18(80));
  });

  it("세션 사용료 → 사용량 기반 로열티 누적", async () => {
    const consent = ethers.keccak256(ethers.toUtf8Bytes("c"));
    await registry.connect(creator).registerVoice(consent, "American", e18(100), e18(2), 8000);
    await coin.connect(learner).approve(await license.getAddress(), e18(200));
    await license.connect(learner).buyLicense(1);
    await license.connect(learner).paySession(1);
    expect(await license.usageCount(1)).to.equal(1);
    // 라이선스 80 + 세션 1.6 = 81.6
    expect(await license.royaltiesOwed(creator.address)).to.equal(e18("81.6"));
  });

  it("스테이킹 + 거버넌스 투표(스테이크 가중)", async () => {
    await coin.transfer(creator.address, e18(2000));
    await coin.connect(creator).approve(await staking.getAddress(), e18(2000));
    await staking.connect(creator).stake(e18(2000));
    expect(await staking.stakedOf(creator.address)).to.equal(e18(2000));

    const id = 1;
    await staking.connect(creator).createProposal("로열티 기본 비율을 85%로", 3600);
    await staking.connect(creator).vote(id, true);
    const p = await staking.proposals(id);
    expect(p.forVotes).to.equal(e18(2000));
  });
});
