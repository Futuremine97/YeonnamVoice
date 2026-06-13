// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title VoiceStaking — VOICE 스테이킹 + 스테이크 가중 거버넌스(시그널링)
/// @notice 토큰을 스테이킹하면 거버넌스 제안에 스테이크 비례로 투표할 수 있다.
/// @dev 실행(executable) 거버넌스가 아니라 시그널링 투표. 정족수/실행은 운영 정책에 위임.
contract VoiceStaking is ReentrancyGuard {
    using SafeERC20 for IERC20;

    IERC20 public immutable token;
    uint256 public totalStaked;
    mapping(address => uint256) public stakedOf;

    uint256 public minStakeToPropose;
    uint256 public proposalCount;

    struct Proposal {
        string  description;
        address proposer;
        uint64  endTime;
        uint256 forVotes;
        uint256 againstVotes;
        bool    closed;
    }
    mapping(uint256 => Proposal) public proposals;
    mapping(uint256 => mapping(address => bool)) public hasVoted;

    event Staked(address indexed user, uint256 amount);
    event Unstaked(address indexed user, uint256 amount);
    event ProposalCreated(uint256 indexed id, address indexed proposer, string description, uint64 endTime);
    event Voted(uint256 indexed id, address indexed voter, bool support, uint256 weight);
    event ProposalClosed(uint256 indexed id, bool passed, uint256 forVotes, uint256 againstVotes);

    constructor(address token_, uint256 minStakeToPropose_) {
        require(token_ != address(0), "zero");
        token = IERC20(token_);
        minStakeToPropose = minStakeToPropose_;
    }

    function stake(uint256 amount) external nonReentrant {
        require(amount > 0, "amount=0");
        token.safeTransferFrom(msg.sender, address(this), amount);
        stakedOf[msg.sender] += amount;
        totalStaked += amount;
        emit Staked(msg.sender, amount);
    }

    function unstake(uint256 amount) external nonReentrant {
        require(amount > 0 && stakedOf[msg.sender] >= amount, "bad amount");
        stakedOf[msg.sender] -= amount;
        totalStaked -= amount;
        token.safeTransfer(msg.sender, amount);
        emit Unstaked(msg.sender, amount);
    }

    function createProposal(string calldata description, uint64 duration) external returns (uint256 id) {
        require(stakedOf[msg.sender] >= minStakeToPropose, "stake too low");
        require(duration >= 1 hours && duration <= 30 days, "bad duration");
        id = ++proposalCount;
        proposals[id] = Proposal({
            description: description,
            proposer: msg.sender,
            endTime: uint64(block.timestamp) + duration,
            forVotes: 0,
            againstVotes: 0,
            closed: false
        });
        emit ProposalCreated(id, msg.sender, description, proposals[id].endTime);
    }

    /// @notice 스테이크 비례 투표. 1주소 1회.
    function vote(uint256 id, bool support) external {
        Proposal storage p = proposals[id];
        require(p.endTime != 0, "no proposal");
        require(block.timestamp < p.endTime, "voting ended");
        require(!hasVoted[id][msg.sender], "already voted");
        uint256 weight = stakedOf[msg.sender];
        require(weight > 0, "no stake");
        hasVoted[id][msg.sender] = true;
        if (support) p.forVotes += weight; else p.againstVotes += weight;
        emit Voted(id, msg.sender, support, weight);
    }

    /// @notice 투표 종료 후 결과 확정(시그널링).
    function closeProposal(uint256 id) external {
        Proposal storage p = proposals[id];
        require(p.endTime != 0 && !p.closed, "bad state");
        require(block.timestamp >= p.endTime, "not ended");
        p.closed = true;
        emit ProposalClosed(id, p.forVotes > p.againstVotes, p.forVotes, p.againstVotes);
    }
}
