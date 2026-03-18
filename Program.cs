using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace Middleware1
{
    static class Program
    {
        public const int MiddlewareId = 1;
        private const int NetworkPort = 8081;
        private static readonly int ReceivePort = 8081 + MiddlewareId; // 8082..8086
        private static readonly int ControlPort = 8086 + MiddlewareId; // 8087..8091

        [STAThread]
        static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MiddlewareForm(MiddlewareId, NetworkPort, ReceivePort, ControlPort));
        }
    }

    sealed class PriorityTag : IComparable<PriorityTag>
    {
        public long Sequence { get; }
        public int ProcessId { get; }

        public PriorityTag(long sequence, int processId)
        {
            Sequence = sequence;
            ProcessId = processId;
        }

        public int CompareTo(PriorityTag other)
        {
            if (other == null) return 1;
            int seqCmp = Sequence.CompareTo(other.Sequence);
            if (seqCmp != 0) return seqCmp;
            return ProcessId.CompareTo(other.ProcessId);
        }

        public override string ToString()
        {
            return $"{Sequence}.{ProcessId:D2}";
        }
    }

    sealed class MessageEntry
    {
        public string MessageId { get; }
        public int SenderId { get; set; }
        public string Content { get; set; }

        public PriorityTag ProposedPriority { get; set; }
        public PriorityTag FinalPriority { get; set; }

        public bool ReceivedFromNetwork { get; set; }
        public bool LocalProposalSent { get; set; }
        public bool Deliverable { get; set; }
        public bool Delivered { get; set; }

        public Dictionary<int, PriorityTag> Proposals { get; }

        public MessageEntry(string messageId, int senderId, string content)
        {
            MessageId = messageId;
            SenderId = senderId;
            Content = content;
            Proposals = new Dictionary<int, PriorityTag>();
        }
    }

    sealed class MiddlewareForm : Form
    {
        private readonly int id;
        private readonly int networkPort;
        private readonly int receivePort;
        private readonly int controlPort;
        private readonly List<int> allIds = new List<int> { 1, 2, 3, 4, 5 };

        private readonly Dictionary<string, MessageEntry> holdback = new Dictionary<string, MessageEntry>();
        private readonly object stateLock = new object();

        private int localMessageCounter;
        private long logicalClock;
        private long highestAgreedSequence;

        private Button sendButton;
        private ListBox sentList;
        private ListBox receivedList;
        private ListBox readyList;

        public MiddlewareForm(int id, int networkPort, int receivePort, int controlPort)
        {
            this.id = id;
            this.networkPort = networkPort;
            this.receivePort = receivePort;
            this.controlPort = controlPort;

            BuildUi();

            new Thread(NetworkListener) { IsBackground = true }.Start();
            new Thread(ControlListener) { IsBackground = true }.Start();
        }

        private void BuildUi()
        {
            Text = $"Middleware {id}";
            Size = new Size(620, 400);

            sendButton = new Button { Text = "Send", Location = new Point(20, 20), Size = new Size(90, 30) };
            sendButton.Click += SendButton_Click;

            var sentLabel = new Label { Text = "Sent", Location = new Point(20, 55), AutoSize = true };
            var receivedLabel = new Label { Text = "Received", Location = new Point(220, 55), AutoSize = true };
            var readyLabel = new Label { Text = "Ready", Location = new Point(420, 55), AutoSize = true };

            sentList = new ListBox { Location = new Point(20, 75), Size = new Size(180, 260) };
            receivedList = new ListBox { Location = new Point(220, 75), Size = new Size(180, 260) };
            readyList = new ListBox { Location = new Point(420, 75), Size = new Size(180, 260) };

            Controls.Add(sendButton);
            Controls.Add(sentLabel);
            Controls.Add(receivedLabel);
            Controls.Add(readyLabel);
            Controls.Add(sentList);
            Controls.Add(receivedList);
            Controls.Add(readyList);
        }

        private void SendButton_Click(object sender, EventArgs e)
        {
            localMessageCounter++;
            string messageId = $"{id}:{localMessageCounter}";
            string content = $"Msg #{localMessageCounter} from Middleware {id} (ID={messageId})";

            lock (stateLock)
            {
                if (!holdback.ContainsKey(messageId))
                {
                    holdback[messageId] = new MessageEntry(messageId, id, content);
                }
            }

            BeginInvoke((Action)(() => sentList.Items.Add(content)));

            ThreadPool.QueueUserWorkItem(_ => SendToNetwork(messageId, id, content));
        }

        private void SendToNetwork(string messageId, int senderId, string content)
        {
            try
            {
                using (var client = new TcpClient())
                {
                    client.Connect("localhost", networkPort);
                    using (var stream = client.GetStream())
                    {
                        string payload = $"MSG;{messageId};{senderId};{content}\n";
                        byte[] data = Encoding.UTF8.GetBytes(payload);
                        stream.Write(data, 0, data.Length);
                    }
                }
            }
            catch
            {
            }
        }

        private void NetworkListener()
        {
            try
            {
                var listener = new TcpListener(IPAddress.Any, receivePort);
                listener.Start();
                while (true)
                {
                    var client = listener.AcceptTcpClient();
                    ThreadPool.QueueUserWorkItem(_ => HandleNetworkClient(client));
                }
            }
            catch
            {
            }
        }

        private void HandleNetworkClient(TcpClient client)
        {
            try
            {
                using (client)
                using (var stream = client.GetStream())
                using (var reader = new System.IO.StreamReader(stream, Encoding.UTF8))
                {
                    string line = reader.ReadLine();
                    if (string.IsNullOrWhiteSpace(line)) return;

                    var parts = line.Split(new[] { ';' }, 4);
                    if (parts.Length != 4 || parts[0] != "MSG") return;

                    string messageId = parts[1];
                    if (!int.TryParse(parts[2], NumberStyles.Integer, CultureInfo.InvariantCulture, out int senderId)) return;
                    string content = parts[3];

                    PriorityTag proposalToSend;
                    bool shouldSendProposal;

                    lock (stateLock)
                    {
                        var entry = GetOrCreateEntry(messageId, senderId, content);
                        entry.SenderId = senderId;
                        entry.Content = content;

                        if (!entry.ReceivedFromNetwork)
                        {
                            entry.ReceivedFromNetwork = true;
                        }

                        if (!entry.LocalProposalSent)
                        {
                            proposalToSend = NextProposalTag();
                            entry.ProposedPriority = proposalToSend;
                            entry.Proposals[id] = proposalToSend;
                            entry.LocalProposalSent = true;
                            shouldSendProposal = true;
                        }
                        else
                        {
                            proposalToSend = entry.ProposedPriority;
                            shouldSendProposal = false;
                        }
                    }

                    BeginInvoke((Action)(() =>
                    {
                        receivedList.Items.Add($"[{proposalToSend}] {content}");
                    }));

                    if (shouldSendProposal)
                    {
                        BroadcastControl($"PROPOSAL;{messageId};{id};{proposalToSend.Sequence};{proposalToSend.ProcessId}");
                    }
                }
            }
            catch
            {
            }
        }

        private void ControlListener()
        {
            try
            {
                var listener = new TcpListener(IPAddress.Any, controlPort);
                listener.Start();
                while (true)
                {
                    var client = listener.AcceptTcpClient();
                    ThreadPool.QueueUserWorkItem(_ => HandleControlClient(client));
                }
            }
            catch
            {
            }
        }

        private void HandleControlClient(TcpClient client)
        {
            try
            {
                using (client)
                using (var stream = client.GetStream())
                using (var reader = new System.IO.StreamReader(stream, Encoding.UTF8))
                {
                    string line = reader.ReadLine();
                    if (string.IsNullOrWhiteSpace(line)) return;

                    var parts = line.Split(';');
                    if (parts.Length < 5) return;

                    string type = parts[0];
                    string messageId = parts[1];
                    if (!int.TryParse(parts[2], NumberStyles.Integer, CultureInfo.InvariantCulture, out int fromId)) return;
                    if (!long.TryParse(parts[3], NumberStyles.Integer, CultureInfo.InvariantCulture, out long seq)) return;
                    if (!int.TryParse(parts[4], NumberStyles.Integer, CultureInfo.InvariantCulture, out int tie)) return;

                    var incomingTag = new PriorityTag(seq, tie);

                    bool sendAgreement = false;
                    PriorityTag agreedTag = null;

                    lock (stateLock)
                    {
                        logicalClock = Math.Max(logicalClock, seq);
                        var entry = GetOrCreateEntry(messageId, ParseSenderId(messageId), messageId);

                        if (type == "PROPOSAL")
                        {
                            entry.Proposals[fromId] = incomingTag;

                            if (entry.SenderId == id && !entry.Deliverable)
                            {
                                bool allProposalsArrived = allIds.All(peerId => entry.Proposals.ContainsKey(peerId));
                                if (allProposalsArrived)
                                {
                                    agreedTag = entry.Proposals.Values.OrderBy(p => p).Last();
                                    InstallAgreement(entry, agreedTag);
                                    sendAgreement = true;
                                }
                            }
                        }
                        else if (type == "AGREEMENT")
                        {
                            InstallAgreement(entry, incomingTag);
                        }
                    }

                    if (sendAgreement && agreedTag != null)
                    {
                        BroadcastControl($"AGREEMENT;{messageId};{id};{agreedTag.Sequence};{agreedTag.ProcessId}");
                    }

                    TryDeliver();
                }
            }
            catch
            {
            }
        }

        private void InstallAgreement(MessageEntry entry, PriorityTag finalTag)
        {
            entry.FinalPriority = finalTag;
            entry.Deliverable = true;
            logicalClock = Math.Max(logicalClock, finalTag.Sequence);
            highestAgreedSequence = Math.Max(highestAgreedSequence, finalTag.Sequence);
        }

        private void TryDeliver()
        {
            while (true)
            {
                MessageEntry toDeliver = null;

                lock (stateLock)
                {
                    var deliverableCandidates = holdback.Values
                        .Where(e => e.ReceivedFromNetwork && e.Deliverable && !e.Delivered)
                        .OrderBy(e => e.FinalPriority)
                        .ToList();

                    if (deliverableCandidates.Count == 0)
                    {
                        return;
                    }

                    var first = deliverableCandidates[0];

                    bool blockedByUndeliverableLower = holdback.Values.Any(e =>
                        e.ReceivedFromNetwork &&
                        !e.Deliverable &&
                        !e.Delivered &&
                        e.ProposedPriority != null &&
                        e.ProposedPriority.CompareTo(first.FinalPriority) < 0);

                    if (blockedByUndeliverableLower)
                    {
                        return;
                    }

                    first.Delivered = true;
                    holdback.Remove(first.MessageId);
                    toDeliver = first;
                }

                if (toDeliver != null)
                {
                    string line = $"[{toDeliver.FinalPriority}] {toDeliver.Content}";
                    BeginInvoke((Action)(() => readyList.Items.Add(line)));
                }
            }
        }

        private MessageEntry GetOrCreateEntry(string messageId, int senderId, string content)
        {
            if (!holdback.TryGetValue(messageId, out var entry))
            {
                entry = new MessageEntry(messageId, senderId, content);
                holdback[messageId] = entry;
            }
            return entry;
        }

        private PriorityTag NextProposalTag()
        {
            long nextSeq = Math.Max(logicalClock, highestAgreedSequence) + 1;
            logicalClock = nextSeq;
            return new PriorityTag(nextSeq, id);
        }

        private void BroadcastControl(string payloadWithoutNewline)
        {
            foreach (int peerId in allIds)
            {
                int peerControlPort = 8086 + peerId;
                ThreadPool.QueueUserWorkItem(_ =>
                {
                    try
                    {
                        using (var client = new TcpClient())
                        {
                            client.Connect("localhost", peerControlPort);
                            using (var stream = client.GetStream())
                            {
                                byte[] data = Encoding.UTF8.GetBytes(payloadWithoutNewline + "\n");
                                stream.Write(data, 0, data.Length);
                            }
                        }
                    }
                    catch
                    {
                    }
                });
            }
        }

        private int ParseSenderId(string messageId)
        {
            int colon = messageId.IndexOf(':');
            if (colon <= 0) return 0;
            string senderText = messageId.Substring(0, colon);
            return int.TryParse(senderText, NumberStyles.Integer, CultureInfo.InvariantCulture, out int senderId)
                ? senderId
                : 0;
        }
    }
}

